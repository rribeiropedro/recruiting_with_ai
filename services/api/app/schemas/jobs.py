from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .shared import ExperienceNodeResult, JobRequirements

JobProcessingStatus = Literal["pending", "scraping", "extracting", "embedded", "failed"]


class JobSubmitRequest(BaseModel):
    url: str | None = Field(None, max_length=2048)
    raw_text: str | None = None

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
    def validate_single_input(self) -> "JobSubmitRequest":
        if bool(self.url) == bool(self.raw_text):
            raise ValueError("Provide exactly one of url or raw_text")
        return self


class JobDescriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str | None
    company_name: str | None
    role_title: str | None
    requirements: JobRequirements
    is_embedded: bool
    status: JobProcessingStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class MatchResult(BaseModel):
    job_description_id: UUID
    job_requirements: JobRequirements
    matched_nodes: list[ExperienceNodeResult]
    low_relevance_warning: bool
