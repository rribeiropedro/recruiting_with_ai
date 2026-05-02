from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .shared import GeneratedApplicationSummary

ApplicationStatus = Literal[
    "pending",
    "scraping",
    "extracting",
    "matching",
    "rewriting",
    "rendering",
    "completed",
    "failed",
]
ResumeTemplate = Literal["modern", "classic", "minimal"]


class GenerateApplicationRequest(BaseModel):
    job_description_id: UUID
    template: ResumeTemplate = "modern"


class GenerateFromUrlRequest(BaseModel):
    url: str | None = Field(None, max_length=2048)
    raw_text: str | None = None
    template: ResumeTemplate = "modern"

    @field_validator("url", "raw_text", mode="before")
    @classmethod
    def blank_strings_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value and not value.startswith("https://"):
            raise ValueError("URL must use HTTPS")
        return value

    @model_validator(mode="after")
    def validate_input_present(self) -> "GenerateFromUrlRequest":
        if not self.url and not self.raw_text:
            raise ValueError("Either url or raw_text must be provided")
        return self


class ApplicationStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ApplicationStatus
    error_message: str | None
    cache_hit: bool
    company_name: str | None
    role_title: str | None
    matched_node_count: int
    pdf_url: str | None
    created_at: datetime
    completed_at: datetime | None


class ApplicationDetailResponse(ApplicationStatusResponse):
    matched_nodes: list[dict[str, Any]]
    similarity_scores: list[float]
    job_requirements: dict[str, Any]


__all__ = [
    "ApplicationDetailResponse",
    "ApplicationStatus",
    "ApplicationStatusResponse",
    "GenerateApplicationRequest",
    "GenerateFromUrlRequest",
    "GeneratedApplicationSummary",
    "ResumeTemplate",
]
