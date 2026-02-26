from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

MAX_FILE_SIZE = 20_971_520  # 20 MB


# ---------------------------------------------------------------------------
# Finding status
# ---------------------------------------------------------------------------


class FindingStatus(StrEnum):
    NORMAL = "normal"
    ABNORMAL_HIGH = "abnormal_high"
    ABNORMAL_LOW = "abnormal_low"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Structured analysis models
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """A single test result or measurement from a medical report."""

    name: str
    value: str
    unit: str | None = None
    status: str  # FindingStatus value or free text from LLM
    reference_range: str | None = None
    explanation: str | None = None


class AnalysisResult(BaseModel):
    """Structured output of a medical report analysis."""

    summary: str
    findings: list[Finding] = []
    alerts: list[str] = []
    recommendations: list[str] = []


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ReportCreate(BaseModel):
    """Create a report record via JSON (Supabase Storage URL flow)."""

    file_url: str
    file_type: str = "unknown"
    original_filename: str | None = None

    @field_validator("file_url")
    @classmethod
    def validate_file_url(cls, v: str) -> str:
        """Reject non-HTTPS URLs and private/internal network addresses."""
        if not v.startswith("https://"):
            raise ValueError("file_url must use HTTPS")
        # Block private/internal IPs and metadata endpoints
        from urllib.parse import urlparse

        hostname = urlparse(v).hostname or ""
        blocked_prefixes = ("10.", "172.", "192.168.", "169.254.", "127.", "0.", "localhost")
        if hostname.startswith(blocked_prefixes):
            raise ValueError("file_url must not point to internal/private addresses")
        return v


class ReportAnalysisResponse(BaseModel):
    id: UUID
    profile_id: UUID
    file_url: str
    file_type: str
    original_filename: str | None
    analysis_result: dict[str, Any] | None
    extracted_facts: list[Any]
    status: str
    error_message: str | None
    disclaimer: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
