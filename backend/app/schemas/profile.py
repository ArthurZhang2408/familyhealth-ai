from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class Relationship(StrEnum):
    SELF = "self"
    PARENT = "parent"
    FATHER = "father"
    MOTHER = "mother"
    SPOUSE = "spouse"
    CHILD = "child"
    SON = "son"
    DAUGHTER = "daughter"
    SIBLING = "sibling"
    BROTHER = "brother"
    SISTER = "sister"
    GRANDPARENT = "grandparent"
    GRANDFATHER = "grandfather"
    GRANDMOTHER = "grandmother"
    OTHER = "other"


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class BloodType(StrEnum):
    A = "A"
    A_POS = "A+"
    A_NEG = "A-"
    B = "B"
    B_POS = "B+"
    B_NEG = "B-"
    AB = "AB"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O = "O"
    O_POS = "O+"
    O_NEG = "O-"


class SmokingStatus(StrEnum):
    NEVER = "never"
    FORMER = "former"
    CURRENT = "current"


class AlcoholFrequency(StrEnum):
    NONE = "none"
    OCCASIONAL = "occasional"
    MODERATE = "moderate"
    HEAVY = "heavy"


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


class SurgicalProcedure(BaseModel):
    procedure: str = Field(min_length=1, max_length=200)
    year: int | None = None


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
    height_cm: float | None = Field(None, gt=0, le=300)
    weight_kg: float | None = Field(None, gt=0, le=500)
    smoking_status: SmokingStatus | None = None
    alcohol_frequency: AlcoholFrequency | None = None
    is_pregnant: bool | None = None
    surgical_history: list[SurgicalProcedure] = []


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
    height_cm: float | None = Field(None, gt=0, le=300)
    weight_kg: float | None = Field(None, gt=0, le=500)
    smoking_status: SmokingStatus | None = None
    alcohol_frequency: AlcoholFrequency | None = None
    is_pregnant: bool | None = None
    surgical_history: list[SurgicalProcedure] | None = None


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
    height_cm: float | None
    weight_kg: float | None
    smoking_status: str | None
    alcohol_frequency: str | None
    is_pregnant: bool | None
    surgical_history: list[SurgicalProcedure]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
