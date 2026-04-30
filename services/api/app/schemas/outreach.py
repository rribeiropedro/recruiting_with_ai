from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CampaignCreateRequest(BaseModel):
    application_id: UUID
    contact_name: str | None = None
    contact_email: str | None = Field(
        None,
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
    )
    contact_title: str | None = None
    contact_linkedin: str | None = None
    auto_discover_contact: bool = True


class CampaignUpdateRequest(BaseModel):
    status: str | None = Field(
        None,
        pattern="^(drafted|queued|meeting_scheduled|rejected|archived)$",
    )
    contact_name: str | None = None
    contact_email: str | None = None
    contact_title: str | None = None
    notes: str | None = None


class DraftEmailRequest(BaseModel):
    tone: str = "conversational"


class SendEmailRequest(BaseModel):
    provider: str = "gmail"
    attach_resume: bool = True


class CampaignResponse(BaseModel):
    id: UUID
    application_id: UUID
    company_name: str | None
    role_title: str | None
    contact_name: str | None
    contact_title: str | None
    contact_email: str | None
    email_verified: bool
    email_subject: str | None
    email_body: str | None
    status: str
    follow_up_count: int
    notes: str | None
    send_error: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CampaignListResponse(BaseModel):
    campaigns: list[CampaignResponse]
    counts: dict[str, int]


class EmailDraftResponse(BaseModel):
    campaign_id: UUID
    email_subject: str
    email_body: str
    company_context_used: dict
    tone: str


class SendResultResponse(BaseModel):
    success: bool
    email_message_id: str | None = None
    error: str | None = None


class OAuthInitiateRequest(BaseModel):
    return_to: str | None = None


class OAuthStatusResponse(BaseModel):
    gmail_connected: bool
    outlook_connected: bool
