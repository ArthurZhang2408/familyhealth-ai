from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int


class ErrorResponse(BaseModel):
    detail: str
    code: str
