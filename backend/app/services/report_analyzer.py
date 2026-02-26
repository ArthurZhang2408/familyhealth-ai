"""ReportAnalyzerService — orchestrates the medical report analysis pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import PurePosixPath
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core import AgentCore
from app.agents.definitions import REPORT_AGENT
from app.agents.session import AgentSession
from app.models.profile import Profile
from app.models.report import ReportAnalysis
from app.schemas.action_log import ActionType
from app.schemas.report import AnalysisResult
from app.services.action_log import ActionLogService
from app.services.context_builder import ContextBuilder
from app.services.llm import ImagePart, LLMMessage, LLMRequest, LLMResponse, LLMTask
from app.services.memory_extractor import MemoryExtractor
from app.services.report_prompts import FACT_EXTRACTION_PROMPT, REPORT_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)

# MIME type mapping from file_type / extension
_EXT_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

_FILE_TYPE_TO_MIME: dict[str, str] = {
    "blood_test": "application/pdf",
    "lab_report": "application/pdf",
    "xray": "image/jpeg",
    "prescription": "image/jpeg",
}


class ReportAnalyzerService:
    """Orchestrates medical report analysis.

    Two-pass LLM strategy:
    - Pass 1 (Gemini, multimodal): Analyze the report image/PDF with profile context.
    - Pass 2 (Qwen, text): Extract discrete facts for Mem0 memory storage.
    """

    def __init__(
        self,
        db: AsyncSession,
        agent_core: AgentCore,
        context_builder: ContextBuilder,
        memory_extractor: MemoryExtractor,
    ) -> None:
        self._db = db
        self._agent = agent_core
        self._ctx = context_builder
        self._mem_extractor = memory_extractor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        report: ReportAnalysis,
        profile: Profile,
        file_bytes: bytes,
    ) -> ReportAnalysis:
        """Run the full analysis pipeline on a medical report.

        Updates the report record in-place (caller is responsible for commit).
        """
        try:
            report.status = "processing"
            await self._db.flush()

            # Resolve MIME type
            mime_type = self._resolve_mime_type(report.file_type, report.original_filename)

            # Build context via ContextBuilder
            query = report.original_filename or "medical report analysis"
            ctx = await self._ctx.build(
                db=self._db,
                profile_id=profile.id,
                query=query,
                interaction_type="report_analysis",
                template=REPORT_ANALYSIS_PROMPT,
            )

            # Pass 1 — Gemini multimodal analysis (agentic if AgentCore available)
            analysis_result = await self._pass1_analyze(
                file_bytes, mime_type, ctx.system_prompt, profile_id=profile.id
            )

            report.analysis_result = analysis_result.model_dump()
            report.status = "completed"

            # Pass 2 — Qwen fact extraction (best-effort)
            extracted_facts = await self._pass2_extract_facts(analysis_result, ctx.system_prompt)
            report.extracted_facts = extracted_facts

            # Log action
            await self._log_action(
                profile,
                ActionType.REPORT_ANALYZED,
                {
                    "report_id": str(report.id),
                    "findings_count": len(analysis_result.findings),
                    "alerts_count": len(analysis_result.alerts),
                },
            )

            await self._db.flush()
            return report

        except Exception as exc:
            logger.exception("Report analysis failed for report %s", report.id)
            report.status = "failed"
            report.error_message = str(exc)
            await self._db.flush()
            return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _pass1_analyze(
        self,
        file_bytes: bytes,
        mime_type: str,
        system_prompt: str,
        profile_id: UUID,
    ) -> AnalysisResult:
        """Pass 1: Gemini multimodal analysis via AgentCore → AnalysisResult."""
        agent_session = AgentSession(
            profile_id=profile_id,
            system_prompt=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Please analyze this medical report.",
                    "image_parts": [ImagePart(data=file_bytes, mime_type=mime_type)],
                }
            ],
        )
        result = await self._agent.run(agent_session, REPORT_AGENT)
        raw = json.loads(result.content)
        return AnalysisResult.model_validate(raw)

    async def _pass2_extract_facts(
        self,
        analysis_result: AnalysisResult,
        system_prompt: str,
    ) -> list[str]:
        """Pass 2: Qwen fact extraction → list of discrete facts for Mem0."""
        try:
            analysis_json = json.dumps(analysis_result.model_dump(), indent=2)
            prompt = FACT_EXTRACTION_PROMPT.format(analysis_json=analysis_json)

            request = LLMRequest(
                task=LLMTask.FACT_EXTRACTION,
                system_prompt=system_prompt,
                messages=[LLMMessage(role="user", content=prompt)],
                temperature=0.0,
                max_tokens=2000,
                response_format={"type": "json"},
            )
            response: LLMResponse = await self._agent.call(request)
            facts = json.loads(response.content)
            if isinstance(facts, list):
                return [str(f) for f in facts]
            return []
        except Exception:
            logger.warning(
                "Pass 2 fact extraction failed, proceeding without facts", exc_info=True
            )
            return []

    @staticmethod
    def _resolve_mime_type(file_type: str, filename: str | None) -> str:
        """Map file_type or filename extension to a MIME type."""
        # Try extension first
        if filename:
            ext = PurePosixPath(filename).suffix.lower()
            if ext in _EXT_TO_MIME:
                return _EXT_TO_MIME[ext]

        # Fall back to file_type mapping
        if file_type in _FILE_TYPE_TO_MIME:
            return _FILE_TYPE_TO_MIME[file_type]

        return "application/octet-stream"

    async def _log_action(
        self,
        profile: Profile,
        action_type: ActionType,
        payload: dict,
    ) -> None:
        """Best-effort action logging."""
        try:
            log_svc = ActionLogService(self._db)
            await log_svc.log(
                profile_id=profile.id,
                account_id=profile.account_id,
                action_type=action_type,
                payload=payload,
            )
        except Exception:
            logger.exception("Action logging failed for %s", action_type)


# ---------------------------------------------------------------------------
# Background analysis function — creates its own DB session
# ---------------------------------------------------------------------------


async def run_analysis_background(
    report_id: UUID,
    profile_id: UUID,
    file_bytes: bytes | None,
    agent_core: AgentCore,
    context_builder: ContextBuilder,
    memory_extractor: MemoryExtractor,
) -> None:
    """Run report analysis as a background task.

    Creates its own DB session to avoid holding the request-scoped session.
    """
    from app.core.database import async_session_factory

    try:
        async with async_session_factory() as db:
            try:
                # Load report and profile
                report = await db.get(ReportAnalysis, report_id)
                if not report:
                    logger.error("Background analysis: report %s not found", report_id)
                    return

                profile = await db.get(Profile, profile_id)
                if not profile:
                    logger.error("Background analysis: profile %s not found", profile_id)
                    return

                # Fetch file bytes if not provided (URL flow)
                if file_bytes is None:
                    if report.file_url.startswith("upload:"):
                        logger.error(
                            "Background analysis: no file bytes and file_url is a "
                            "placeholder (%s) for report %s",
                            report.file_url,
                            report_id,
                        )
                        report.status = "failed"
                        report.error_message = (
                            "File data unavailable. Please re-upload the report."
                        )
                        await db.commit()
                        return
                    file_bytes = await _fetch_file(report.file_url)

                # Run analysis
                svc = ReportAnalyzerService(db, agent_core, context_builder, memory_extractor)
                report = await svc.analyze(report, profile, file_bytes)

                await db.commit()

                # Background memory extraction (best-effort, after commit)
                if report.status == "completed" and report.extracted_facts:
                    try:
                        fact_messages = [
                            {
                                "role": "assistant",
                                "content": "Medical report analysis results:\n"
                                + "\n".join(f"- {f}" for f in report.extracted_facts),
                            }
                        ]
                        await memory_extractor.extract_and_store(
                            profile_id=profile_id,
                            messages=fact_messages,
                            source=f"report:{report_id}",
                            category="lab_results",
                        )
                    except Exception:
                        logger.exception("Memory extraction failed for report %s", report_id)

            except Exception:
                await db.rollback()
                # Try to mark report as failed
                try:
                    report = await db.get(ReportAnalysis, report_id)
                    if report and report.status != "failed":
                        report.status = "failed"
                        report.error_message = "Background analysis encountered an error"
                        await db.commit()
                except Exception:
                    logger.exception("Failed to mark report %s as failed", report_id)
                raise

    except Exception:
        logger.exception("Background analysis failed for report %s", report_id)


async def _fetch_file(file_url: str) -> bytes:
    """Download file bytes from a URL (e.g., Supabase Storage)."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(file_url)
        response.raise_for_status()
        return response.content
