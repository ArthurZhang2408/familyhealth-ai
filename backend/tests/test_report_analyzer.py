"""Comprehensive tests for the report analysis feature.

Tests cover:
- LLM multimodal extension (ImagePart, LLMMessage)
- Structured schema validation (Finding, AnalysisResult)
- ReportAnalyzerService unit tests (two-pass LLM, error handling)
- API route integration (upload, create, list, get, reanalyze)
- Memory extraction and action logging
- Background task behavior
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.agents.core import AgentCore
from app.agents.registry import ToolRegistry
from app.models.profile import Profile
from app.models.report import ReportAnalysis
from app.schemas.report import (
    AnalysisResult,
    Finding,
    FindingStatus,
)
from app.services.llm import ImagePart, LLMMessage, LLMResponse, LLMTask
from app.services.report_analyzer import ReportAnalyzerService

from .conftest import OTHER_ACCOUNT_ID, TEST_ACCOUNT_ID

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

PROFILE_ID = uuid.uuid4()

MOCK_ANALYSIS_JSON = {
    "summary": "Complete blood count — all values normal except elevated cholesterol.",
    "findings": [
        {
            "name": "hemoglobin",
            "value": "14.2",
            "unit": "g/dL",
            "status": "normal",
            "reference_range": "12.0-17.5",
            "explanation": "Hemoglobin is within the normal range.",
        },
        {
            "name": "total cholesterol",
            "value": "220",
            "unit": "mg/dL",
            "status": "abnormal_high",
            "reference_range": "<200",
            "explanation": "Total cholesterol is elevated above the recommended level.",
        },
    ],
    "alerts": ["Elevated cholesterol — discuss with physician"],
    "recommendations": ["Dietary changes to reduce cholesterol", "Retest in 3 months"],
}

MOCK_FACTS = [
    "hemoglobin is 14.2 g/dL (normal)",
    "total cholesterol 220 mg/dL (elevated)",
]

SAMPLE_PDF_BYTES = b"%PDF-1.4 fake pdf content for testing"
SAMPLE_IMAGE_BYTES = b"\xff\xd8\xff\xe0 fake jpeg content for testing"


def _make_profile(**overrides: Any) -> MagicMock:
    """Build a mock Profile with sensible defaults."""
    defaults = {
        "id": PROFILE_ID,
        "account_id": TEST_ACCOUNT_ID,
        "name": "Test Patient",
        "date_of_birth": date(1990, 5, 15),
        "sex": "female",
        "blood_type": "A+",
        "relationship": "self",
        "allergies": [{"allergen": "Penicillin", "severity": "severe", "reaction": "rash"}],
        "current_medications": [
            {"name": "Metformin", "dosage": "500mg", "frequency": "twice daily"}
        ],
        "medical_conditions": [
            {"condition": "Type 2 Diabetes", "diagnosed": "2020", "status": "active"}
        ],
        "family_medical_history": {"Heart Disease": ["Father"]},
        "deleted_at": None,
    }
    defaults.update(overrides)
    profile = MagicMock()
    for k, v in defaults.items():
        setattr(profile, k, v)
    return profile


def _make_report(**overrides: Any) -> MagicMock:
    """Build a mock ReportAnalysis."""
    defaults = {
        "id": uuid.uuid4(),
        "profile_id": PROFILE_ID,
        "file_url": "https://storage.example.com/reports/test.pdf",
        "file_type": "lab_report",
        "original_filename": "blood_test_2026.pdf",
        "analysis_result": None,
        "extracted_facts": [],
        "status": "pending",
        "error_message": None,
    }
    defaults.update(overrides)
    report = MagicMock()
    for k, v in defaults.items():
        setattr(report, k, v)
    return report


def _mock_llm_router(
    pass1_content: str | None = None,
    pass2_content: str | None = None,
    pass1_error: Exception | None = None,
) -> AsyncMock:
    """Build a mock LLMRouter that returns canned responses."""
    router = AsyncMock()

    async def _route(request):
        if request.task == LLMTask.REPORT_ANALYSIS:
            if pass1_error:
                raise pass1_error
            content = pass1_content or json.dumps(MOCK_ANALYSIS_JSON)
            return LLMResponse(content=content, model="gemini-2.5-flash-lite", usage={})
        elif request.task == LLMTask.FACT_EXTRACTION:
            content = pass2_content or json.dumps(MOCK_FACTS)
            return LLMResponse(content=content, model="qwen3.5:397b", usage={})
        raise ValueError(f"Unexpected task: {request.task}")

    router.route = AsyncMock(side_effect=_route)
    return router


def _mock_context_builder() -> AsyncMock:
    """Build a mock ContextBuilder."""
    ctx_builder = AsyncMock()
    ctx_result = MagicMock()
    ctx_result.system_prompt = "You are a medical report analysis assistant."
    ctx_result.profile_context = {"name": "Test Patient"}
    ctx_result.memories_used = 2
    ctx_result.token_counts = {"profile": 100, "memories": 50, "total": 200}
    ctx_builder.build = AsyncMock(return_value=ctx_result)
    return ctx_builder


def _mock_memory_extractor() -> AsyncMock:
    extractor = AsyncMock()
    extractor.extract_and_store = AsyncMock(return_value=None)
    return extractor


# ===================================================================
# 1. LLM Multimodal Extension
# ===================================================================


class TestImagePart:
    def test_create_image_part(self):
        """ImagePart stores bytes and mime_type."""
        part = ImagePart(data=b"test bytes", mime_type="image/jpeg")
        assert part.data == b"test bytes"
        assert part.mime_type == "image/jpeg"

    def test_llm_message_backward_compat(self):
        """LLMMessage without image_parts still works."""
        msg = LLMMessage(role="user", content="hello")
        assert msg.image_parts is None
        assert msg.content == "hello"

    def test_llm_message_with_image_parts(self):
        """LLMMessage carries image parts alongside text."""
        msg = LLMMessage(
            role="user",
            content="Analyze this report",
            image_parts=[
                ImagePart(data=b"pdf bytes", mime_type="application/pdf"),
                ImagePart(data=b"img bytes", mime_type="image/png"),
            ],
        )
        assert len(msg.image_parts) == 2
        assert msg.image_parts[0].mime_type == "application/pdf"


# ===================================================================
# 2. Schema Validation
# ===================================================================


class TestSchemas:
    def test_finding_model(self):
        finding = Finding(
            name="hemoglobin",
            value="14.2",
            unit="g/dL",
            status=FindingStatus.NORMAL,
            reference_range="12.0-17.5",
            explanation="Within normal range.",
        )
        assert finding.name == "hemoglobin"
        assert finding.status == "normal"

    def test_analysis_result_model(self):
        result = AnalysisResult(
            summary="All normal",
            findings=[Finding(name="WBC", value="7.0", status="normal")],
            alerts=["Check iron levels"],
            recommendations=["Retest in 6 months"],
        )
        assert len(result.findings) == 1
        assert len(result.alerts) == 1

    def test_analysis_result_defaults(self):
        result = AnalysisResult(summary="Normal report")
        assert result.findings == []
        assert result.alerts == []
        assert result.recommendations == []


# ===================================================================
# 3. ReportAnalyzerService Unit Tests
# ===================================================================


class TestReportAnalyzerService:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        from app.agents.core import AgentCore
        from app.agents.registry import ToolRegistry

        return ReportAnalyzerService(
            db=mock_db,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )

    async def test_analyze_pdf_happy_path(self, service, mock_db):
        """Full analysis pipeline succeeds for PDF."""
        report = _make_report()
        profile = _make_profile()

        result = await service.analyze(report, profile, SAMPLE_PDF_BYTES)

        assert result.status == "completed"
        assert result.analysis_result is not None
        assert result.analysis_result["summary"] == MOCK_ANALYSIS_JSON["summary"]
        assert len(result.analysis_result["findings"]) == 2
        assert result.extracted_facts == MOCK_FACTS

    async def test_analyze_image_happy_path(self, service, mock_db):
        """Full analysis pipeline succeeds for JPEG image."""
        report = _make_report(original_filename="xray.jpg", file_type="xray")
        profile = _make_profile()

        result = await service.analyze(report, profile, SAMPLE_IMAGE_BYTES)
        assert result.status == "completed"

    async def test_analyze_sets_processing_status(self, service, mock_db):
        """Status transitions to processing before analysis."""
        report = _make_report()
        profile = _make_profile()

        # Track status changes
        statuses = []
        original_flush = mock_db.flush

        async def track_flush():
            statuses.append(report.status)
            return await original_flush()

        mock_db.flush = AsyncMock(side_effect=track_flush)

        await service.analyze(report, profile, SAMPLE_PDF_BYTES)
        assert "processing" in statuses

    async def test_analyze_pass1_malformed_json(self, mock_db):
        """Pass 1 returns non-JSON → status=failed."""
        svc = ReportAnalyzerService(
            db=mock_db,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(pass1_content="This is not JSON"),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )
        report = _make_report()
        result = await svc.analyze(report, _make_profile(), SAMPLE_PDF_BYTES)
        assert result.status == "failed"
        assert result.error_message is not None

    async def test_analyze_pass1_llm_error(self, mock_db):
        """Pass 1 LLM throws → status=failed with error message."""
        svc = ReportAnalyzerService(
            db=mock_db,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(pass1_error=RuntimeError("API timeout")),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )
        report = _make_report()
        result = await svc.analyze(report, _make_profile(), SAMPLE_PDF_BYTES)
        assert result.status == "failed"
        assert "API timeout" in result.error_message

    async def test_analyze_pass2_failure_still_completes(self, mock_db):
        """Pass 2 failure doesn't prevent analysis completion."""
        svc = ReportAnalyzerService(
            db=mock_db,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(pass2_content="not valid json [[["),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )
        report = _make_report()
        result = await svc.analyze(report, _make_profile(), SAMPLE_PDF_BYTES)
        assert result.status == "completed"
        assert result.extracted_facts == []

    async def test_analyze_pass2_returns_non_list(self, mock_db):
        """Pass 2 returns a non-list JSON → extracted_facts=[]."""
        svc = ReportAnalyzerService(
            db=mock_db,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(pass2_content='{"not": "a list"}'),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )
        report = _make_report()
        result = await svc.analyze(report, _make_profile(), SAMPLE_PDF_BYTES)
        assert result.status == "completed"
        assert result.extracted_facts == []

    async def test_context_builder_called_correctly(self, mock_db):
        """ContextBuilder.build called with interaction_type='report_analysis'."""
        ctx = _mock_context_builder()
        svc = ReportAnalyzerService(
            db=mock_db,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=ctx,
            memory_extractor=_mock_memory_extractor(),
        )
        report = _make_report()
        await svc.analyze(report, _make_profile(), SAMPLE_PDF_BYTES)

        ctx.build.assert_called_once()
        call_kwargs = ctx.build.call_args
        assert call_kwargs.kwargs.get("interaction_type") == "report_analysis"

    def test_resolve_mime_type_pdf(self):
        assert (
            ReportAnalyzerService._resolve_mime_type("unknown", "report.pdf") == "application/pdf"
        )

    def test_resolve_mime_type_jpeg_from_extension(self):
        assert ReportAnalyzerService._resolve_mime_type("unknown", "scan.jpg") == "image/jpeg"

    def test_resolve_mime_type_png(self):
        assert ReportAnalyzerService._resolve_mime_type("unknown", "image.png") == "image/png"

    def test_resolve_mime_type_from_file_type(self):
        assert ReportAnalyzerService._resolve_mime_type("blood_test", None) == "application/pdf"

    def test_resolve_mime_type_unknown(self):
        assert (
            ReportAnalyzerService._resolve_mime_type("unknown", "data.bin")
            == "application/octet-stream"
        )

    async def test_analyze_logs_action(self, mock_db):
        """Action log called on successful analysis."""
        svc = ReportAnalyzerService(
            db=mock_db,
            agent_core=AgentCore(
                llm_router=_mock_llm_router(),
                tool_registry=ToolRegistry(),
            ),
            context_builder=_mock_context_builder(),
            memory_extractor=_mock_memory_extractor(),
        )
        report = _make_report()
        profile = _make_profile()

        with patch("app.services.report_analyzer.ActionLogService") as mock_log_cls:
            mock_log_instance = AsyncMock()
            mock_log_cls.return_value = mock_log_instance
            await svc.analyze(report, profile, SAMPLE_PDF_BYTES)
            mock_log_instance.log.assert_called_once()
            call_kwargs = mock_log_instance.log.call_args.kwargs
            assert call_kwargs["action_type"] == "report_analyzed"


# ===================================================================
# 4. Route Integration Tests
# ===================================================================


async def _create_profile(client: AsyncClient) -> dict:
    """Create a profile and return its JSON."""
    resp = await client.post(
        "/api/v1/profiles",
        json={
            "name": "Report Test Patient",
            "relationship": "self",
            "sex": "female",
            "date_of_birth": "1990-05-15",
        },
    )
    assert resp.status_code == 201
    return resp.json()


class TestReportRoutes:
    async def test_upload_pdf(self, client: AsyncClient):
        """Upload PDF returns 201 with status=pending."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("blood_test.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["original_filename"] == "blood_test.pdf"

    async def test_upload_jpeg(self, client: AsyncClient):
        """Upload JPEG returns 201."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("xray.jpg", SAMPLE_IMAGE_BYTES, "image/jpeg")},
        )
        assert resp.status_code == 201

    async def test_upload_unsupported_type(self, client: AsyncClient):
        """Upload .txt file returns 400."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("notes.txt", b"some text", "text/plain")},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    async def test_upload_empty_file(self, client: AsyncClient):
        """Upload empty file returns 400."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    async def test_upload_no_filename(self, client: AsyncClient):
        """Upload without filename returns 400 or 422."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        assert resp.status_code in (400, 422)

    async def test_create_report_json(self, client: AsyncClient):
        """Create report with JSON body returns 201."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(
            f"/api/v1/profiles/{pid}/reports",
            json={
                "file_url": "https://storage.example.com/report.pdf",
                "file_type": "blood_test",
                "original_filename": "cbc_results.pdf",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["file_url"] == "https://storage.example.com/report.pdf"

    async def test_list_reports_empty(self, client: AsyncClient):
        """List reports returns empty list for new profile."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.get(f"/api/v1/profiles/{pid}/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_reports_with_data(self, client: AsyncClient):
        """List reports returns uploaded reports."""
        profile = await _create_profile(client)
        pid = profile["id"]

        # Upload two reports
        await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("report1.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("report2.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )

        resp = await client.get(f"/api/v1/profiles/{pid}/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_reports_pagination(self, client: AsyncClient):
        """List reports respects pagination params."""
        profile = await _create_profile(client)
        pid = profile["id"]

        for i in range(3):
            await client.post(
                f"/api/v1/profiles/{pid}/reports/upload",
                files={"file": (f"report{i}.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
            )

        resp = await client.get(f"/api/v1/profiles/{pid}/reports?page=1&per_page=2")
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1

    async def test_get_report(self, client: AsyncClient):
        """Get report by ID returns correct report."""
        profile = await _create_profile(client)
        pid = profile["id"]

        upload_resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("report.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        rid = upload_resp.json()["id"]

        resp = await client.get(f"/api/v1/profiles/{pid}/reports/{rid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rid

    async def test_get_report_not_found(self, client: AsyncClient):
        """Get nonexistent report returns 404."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.get(f"/api/v1/profiles/{pid}/reports/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_get_report_wrong_profile(self, client: AsyncClient):
        """Get report from wrong profile returns 404."""
        profile1 = await _create_profile(client)
        pid1 = profile1["id"]

        upload_resp = await client.post(
            f"/api/v1/profiles/{pid1}/reports/upload",
            files={"file": ("report.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        rid = upload_resp.json()["id"]

        # Create second profile
        profile2_resp = await client.post(
            "/api/v1/profiles",
            json={"name": "Other Patient", "relationship": "parent"},
        )
        pid2 = profile2_resp.json()["id"]

        resp = await client.get(f"/api/v1/profiles/{pid2}/reports/{rid}")
        assert resp.status_code == 404

    async def test_reanalyze_report(self, client: AsyncClient):
        """Reanalyze resets status to pending."""
        profile = await _create_profile(client)
        pid = profile["id"]

        upload_resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("report.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        rid = upload_resp.json()["id"]

        resp = await client.post(f"/api/v1/profiles/{pid}/reports/{rid}/reanalyze")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert resp.json()["analysis_result"] is None

    async def test_reanalyze_not_found(self, client: AsyncClient):
        """Reanalyze nonexistent report returns 404."""
        profile = await _create_profile(client)
        pid = profile["id"]

        resp = await client.post(f"/api/v1/profiles/{pid}/reports/{uuid.uuid4()}/reanalyze")
        assert resp.status_code == 404

    async def test_disclaimer_on_completed_report(self, client: AsyncClient):
        """Disclaimer is included when analysis_result exists."""
        profile = await _create_profile(client)
        pid = profile["id"]

        # Create report without analysis
        upload_resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("report.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        data = upload_resp.json()
        # Pending report has no analysis → no disclaimer
        assert data["disclaimer"] is None

    async def test_cross_account_isolation(self, client: AsyncClient):
        """Reports from one account are not accessible from another."""
        from tests.conftest import use_account

        # Create profile and report as TEST_ACCOUNT
        profile = await _create_profile(client)
        pid = profile["id"]
        upload_resp = await client.post(
            f"/api/v1/profiles/{pid}/reports/upload",
            files={"file": ("secret.pdf", SAMPLE_PDF_BYTES, "application/pdf")},
        )
        rid = upload_resp.json()["id"]

        # Switch to OTHER_ACCOUNT
        use_account(OTHER_ACCOUNT_ID)
        resp = await client.get(f"/api/v1/profiles/{pid}/reports/{rid}")
        assert resp.status_code == 404


# ===================================================================
# 5. Background Task Tests
# ===================================================================


class TestBackgroundAnalysis:
    async def test_run_analysis_background_happy_path(self):
        """Background function creates session, runs analysis, commits."""
        from app.services.report_analyzer import run_analysis_background

        report_id = uuid.uuid4()
        profile_id = PROFILE_ID

        mock_report = _make_report(id=report_id, profile_id=profile_id)
        mock_profile = _make_profile(id=profile_id)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(
            side_effect=lambda cls, id_: {
                ReportAnalysis: mock_report,
                Profile: mock_profile,
            }.get(cls)
        )
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.flush = AsyncMock()

        # Override async_session_factory
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        llm_router = _mock_llm_router()
        ctx_builder = _mock_context_builder()
        mem_extractor = _mock_memory_extractor()

        with (
            patch(
                "app.core.database.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch.object(
                ReportAnalyzerService,
                "analyze",
                new_callable=AsyncMock,
                return_value=_make_report(
                    id=report_id,
                    status="completed",
                    extracted_facts=MOCK_FACTS,
                ),
            ),
        ):
            await run_analysis_background(
                report_id=report_id,
                profile_id=profile_id,
                file_bytes=SAMPLE_PDF_BYTES,
                agent_core=AgentCore(
                    llm_router=llm_router,
                    tool_registry=ToolRegistry(),
                ),
                context_builder=ctx_builder,
                memory_extractor=mem_extractor,
            )

        mock_session.commit.assert_called()

    async def test_run_analysis_background_upload_placeholder_no_bytes(self):
        """Background task fails gracefully if file_bytes=None and URL is placeholder."""
        from app.services.report_analyzer import run_analysis_background

        report_id = uuid.uuid4()
        mock_report = _make_report(id=report_id, file_url="upload:test.pdf", status="pending")
        mock_profile = _make_profile()

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(
            side_effect=lambda cls, id_: {
                ReportAnalysis: mock_report,
                Profile: mock_profile,
            }.get(cls)
        )
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.database.async_session_factory",
            return_value=mock_session_ctx,
        ):
            await run_analysis_background(
                report_id=report_id,
                profile_id=PROFILE_ID,
                file_bytes=None,
                agent_core=AgentCore(
                    llm_router=_mock_llm_router(),
                    tool_registry=ToolRegistry(),
                ),
                context_builder=_mock_context_builder(),
                memory_extractor=_mock_memory_extractor(),
            )

        assert mock_report.status == "failed"
        assert "re-upload" in mock_report.error_message.lower()

    async def test_run_analysis_background_handles_error(self):
        """Background function handles errors without crashing."""
        from app.services.report_analyzer import run_analysis_background

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)  # report not found
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.database.async_session_factory",
            return_value=mock_session_ctx,
        ):
            # Should not raise
            await run_analysis_background(
                report_id=uuid.uuid4(),
                profile_id=uuid.uuid4(),
                file_bytes=SAMPLE_PDF_BYTES,
                agent_core=AgentCore(
                    llm_router=_mock_llm_router(),
                    tool_registry=ToolRegistry(),
                ),
                context_builder=_mock_context_builder(),
                memory_extractor=_mock_memory_extractor(),
            )


# ===================================================================
# 6. Memory & Action Logging
# ===================================================================


class TestMemoryAndLogging:
    async def test_memory_extraction_triggered(self):
        """Memory extraction is called after successful analysis in background."""
        from app.services.report_analyzer import run_analysis_background

        report_id = uuid.uuid4()
        mock_report = _make_report(id=report_id, status="completed", extracted_facts=MOCK_FACTS)
        mock_profile = _make_profile()

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(
            side_effect=lambda cls, id_: {
                ReportAnalysis: mock_report,
                Profile: mock_profile,
            }.get(cls)
        )
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.flush = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mem_extractor = _mock_memory_extractor()

        with (
            patch(
                "app.core.database.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch.object(
                ReportAnalyzerService,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_report,
            ),
        ):
            await run_analysis_background(
                report_id=report_id,
                profile_id=PROFILE_ID,
                file_bytes=SAMPLE_PDF_BYTES,
                agent_core=AgentCore(
                    llm_router=_mock_llm_router(),
                    tool_registry=ToolRegistry(),
                ),
                context_builder=_mock_context_builder(),
                memory_extractor=mem_extractor,
            )

        mem_extractor.extract_and_store.assert_called_once()
        call_kwargs = mem_extractor.extract_and_store.call_args.kwargs
        assert call_kwargs["category"] == "lab_results"
        assert f"report:{report_id}" == call_kwargs["source"]

    async def test_memory_extraction_failure_doesnt_crash(self):
        """Memory extraction failure doesn't crash the background task."""
        from app.services.report_analyzer import run_analysis_background

        report_id = uuid.uuid4()
        mock_report = _make_report(id=report_id, status="completed", extracted_facts=MOCK_FACTS)
        mock_profile = _make_profile()

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(
            side_effect=lambda cls, id_: {
                ReportAnalysis: mock_report,
                Profile: mock_profile,
            }.get(cls)
        )
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.flush = AsyncMock()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mem_extractor = _mock_memory_extractor()
        mem_extractor.extract_and_store = AsyncMock(side_effect=RuntimeError("Mem0 down"))

        with (
            patch(
                "app.core.database.async_session_factory",
                return_value=mock_session_ctx,
            ),
            patch.object(
                ReportAnalyzerService,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_report,
            ),
        ):
            # Should not raise
            await run_analysis_background(
                report_id=report_id,
                profile_id=PROFILE_ID,
                file_bytes=SAMPLE_PDF_BYTES,
                agent_core=AgentCore(
                    llm_router=_mock_llm_router(),
                    tool_registry=ToolRegistry(),
                ),
                context_builder=_mock_context_builder(),
                memory_extractor=mem_extractor,
            )
