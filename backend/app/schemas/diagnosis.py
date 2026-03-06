from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DiagnosisPhase(StrEnum):
    TRIAGE = "triage"
    CHARACTERIZATION = "characterization"
    SYSTEM_REVIEW = "system_review"
    SELF_TESTS = "self_tests"
    RISK_FACTORS = "risk_factors"
    DIFFERENTIAL = "differential"
    FOLLOW_UP = "follow_up"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    MODERATE = "moderate"
    MILD = "mild"
    INFORMATIONAL = "informational"


class DiagnosisUrgency(StrEnum):
    EMERGENCY = "emergency"
    SEE_DOCTOR_TODAY = "see_doctor_today"
    SEE_DOCTOR_THIS_WEEK = "see_doctor_this_week"
    SEE_DOCTOR_SOON = "see_doctor_soon"
    MONITOR_AT_HOME = "monitor_at_home"


# ---------------------------------------------------------------------------
# Structured diagnosis output schemas
# ---------------------------------------------------------------------------


class DifferentialDiagnosis(BaseModel):
    condition: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    action_plan: str
    urgency: DiagnosisUrgency


class InformationGathered(BaseModel):
    chief_complaint: str | None = None
    onset: str | None = None
    location: str | None = None
    duration: str | None = None
    character: str | None = None
    aggravating_factors: str | None = None
    relieving_factors: str | None = None
    temporal_pattern: str | None = None
    severity_rating: str | None = None
    associated_symptoms: list[str] = Field(default_factory=list)
    self_test_results: list[str] = Field(default_factory=list)
    relevant_risk_factors: list[str] = Field(default_factory=list)


class DiagnosisState(BaseModel):
    phase: DiagnosisPhase
    turn_number: int = 0
    severity: Severity = Severity.MODERATE
    red_flags_detected: list[str] = Field(default_factory=list)
    information_gathered: InformationGathered = Field(default_factory=InformationGathered)
    differential_diagnoses: list[DifferentialDiagnosis] = Field(default_factory=list)
    suggested_next_questions: list[str] = Field(default_factory=list)
    ready_for_differential: bool = False
    drug_interaction_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class DiagnosisSessionCreate(BaseModel):
    chief_complaint: str


class DiagnosisSessionUpdate(BaseModel):
    status: Literal["active", "resolved", "abandoned"] | None = None
    resolution_notes: str | None = None


class DiagnosisMessageCreate(BaseModel):
    content: str


class DiagnosisMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    content_parts: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = Field(None, validation_alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class DiagnosisSessionResponse(BaseModel):
    id: UUID
    profile_id: UUID
    status: str
    chief_complaint: str | None
    differential_diagnoses: list[dict[str, Any]]
    resolution_notes: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiagnosisSessionDetailResponse(DiagnosisSessionResponse):
    messages: list[DiagnosisMessageResponse] = []


class DiagnosisTurnResponse(BaseModel):
    """Response for create_session and send_message — includes AI response + state."""

    message: DiagnosisMessageResponse
    diagnosis_state: DiagnosisState
    disclaimer: str
