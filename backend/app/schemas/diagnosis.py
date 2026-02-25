from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


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
    created_at: datetime

    model_config = {"from_attributes": True}


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
