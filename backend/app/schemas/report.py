from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ReportCreate(BaseModel):
    file_url: str
    file_type: str = "unknown"
    original_filename: str | None = None


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
