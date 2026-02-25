from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileCreate(BaseModel):
    name: str
    relationship: str = Field(pattern=r"^(self|parent|spouse|child|sibling|other)$")
    sex: str | None = Field(None, pattern=r"^(male|female|other)$")
    date_of_birth: date | None = None
    blood_type: str | None = Field(None, pattern=r"^(A|B|AB|O)[+-]$")
    allergies: list[dict[str, Any]] = []
    current_medications: list[dict[str, Any]] = []
    medical_conditions: list[dict[str, Any]] = []
    family_medical_history: dict[str, Any] = {}
    emergency_contacts: list[dict[str, Any]] = []


class ProfileUpdate(BaseModel):
    name: str | None = None
    relationship: str | None = Field(None, pattern=r"^(self|parent|spouse|child|sibling|other)$")
    sex: str | None = Field(None, pattern=r"^(male|female|other)$")
    date_of_birth: date | None = None
    blood_type: str | None = Field(None, pattern=r"^(A|B|AB|O)[+-]$")
    allergies: list[dict[str, Any]] | None = None
    current_medications: list[dict[str, Any]] | None = None
    medical_conditions: list[dict[str, Any]] | None = None
    family_medical_history: dict[str, Any] | None = None
    emergency_contacts: list[dict[str, Any]] | None = None


class ProfileResponse(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    relationship: str
    sex: str | None
    date_of_birth: date | None
    blood_type: str | None
    allergies: list[dict[str, Any]]
    current_medications: list[dict[str, Any]]
    medical_conditions: list[dict[str, Any]]
    family_medical_history: dict[str, Any]
    emergency_contacts: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
