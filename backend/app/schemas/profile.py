from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Relationship(StrEnum):
    SELF = "self"
    PARENT = "parent"
    SPOUSE = "spouse"
    CHILD = "child"
    SIBLING = "sibling"
    OTHER = "other"


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class BloodType(StrEnum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"


class AllergySeverity(StrEnum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class ConditionStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    MANAGED = "managed"


class Allergy(BaseModel):
    allergen: str = Field(min_length=1, max_length=200)
    severity: AllergySeverity
    reaction: str | None = None


class Medication(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)


class MedicalCondition(BaseModel):
    condition: str = Field(min_length=1, max_length=200)
    diagnosed: str | None = None
    status: ConditionStatus


class EmergencyContact(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=30)
    relationship: str = Field(min_length=1, max_length=50)


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    relationship: Relationship
    sex: Sex | None = None
    date_of_birth: date | None = None
    blood_type: BloodType | None = None
    allergies: list[Allergy] = []
    current_medications: list[Medication] = []
    medical_conditions: list[MedicalCondition] = []
    family_medical_history: dict[str, list[str]] = {}
    emergency_contacts: list[EmergencyContact] = []


class ProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    relationship: Relationship | None = None
    sex: Sex | None = None
    date_of_birth: date | None = None
    blood_type: BloodType | None = None
    allergies: list[Allergy] | None = None
    current_medications: list[Medication] | None = None
    medical_conditions: list[MedicalCondition] | None = None
    family_medical_history: dict[str, list[str]] | None = None
    emergency_contacts: list[EmergencyContact] | None = None


class ProfileResponse(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    relationship: str
    sex: str | None
    date_of_birth: date | None
    blood_type: str | None
    allergies: list[Allergy]
    current_medications: list[Medication]
    medical_conditions: list[MedicalCondition]
    family_medical_history: dict[str, list[str]]
    emergency_contacts: list[EmergencyContact]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
