from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class ActionType(StrEnum):
    PROFILE_CREATED = "profile_created"
    PROFILE_UPDATED = "profile_updated"
    PROFILE_DELETED = "profile_deleted"
    DIAGNOSIS_STARTED = "diagnosis_started"
    DIAGNOSIS_MESSAGE = "diagnosis_message"
    DIAGNOSIS_RESOLVED = "diagnosis_resolved"
    REPORT_UPLOADED = "report_uploaded"
    REPORT_ANALYZED = "report_analyzed"
    CHAT_MESSAGE = "chat_message"
    MEMORY_UPDATED = "memory_updated"
    MEMORY_EXTRACTED = "memory_extracted"
    MEMORY_DELETED = "memory_deleted"


class ActionLogResponse(BaseModel):
    id: int
    profile_id: UUID
    account_id: UUID
    action_type: ActionType
    payload: dict
    created_at: datetime

    model_config = {"from_attributes": True}
