from datetime import date
from uuid import UUID

from pydantic import BaseModel


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
    company_name: str | None
    role_title: str | None
    technical_skills: list[str]
    soft_skills: list[str]
    responsibilities: list[str]
    experience_years: int | None
    education: str | None
    nice_to_haves: list[str]
    industry: str | None


class GeneratedApplicationSummary(BaseModel):
    application_id: UUID
    job_description_id: UUID
    company_name: str | None
    role_title: str | None
    pdf_storage_path: str
    pdf_url: str
    tailored_content: dict
    resume_text_summary: str
