from datetime import date
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator


class ExperienceNodeResult(BaseModel):
    id: UUID
    title: str
    organization: str | None
    role: str | None
    start_date: date | None
    end_date: date | None
    description: str
    bullet_points: list[str]
    node_type: str
    tags: list[str]
    similarity_score: float


class JobRequirements(BaseModel):
    company_name: str | None = None
    role_title: str | None = None
    technical_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    experience_years: int | None = None
    education: str | None = None
    nice_to_haves: list[str] = Field(default_factory=list)
    industry: str | None = None

    @field_validator("experience_years", mode="before")
    @classmethod
    def parse_experience_years(cls, value: object) -> object:
        if isinstance(value, str):
            digits = "".join(char for char in value if char.isdigit())
            return int(digits) if digits else None
        return value


class GeneratedApplicationSummary(BaseModel):
    application_id: UUID
    job_description_id: UUID
    company_name: str | None
    role_title: str | None
    pdf_storage_path: str
    pdf_url: str
    tailored_content: dict[str, Any]
    resume_text_summary: str = Field(
        validation_alias=AliasChoices("resume_text_summary", "resume_summary")
    )
