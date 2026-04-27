from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, TIMESTAMP, ForeignKey, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OutreachCampaign(Base):
    __tablename__ = "outreach_campaigns"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    application_id = Column(PGUUID(as_uuid=True), ForeignKey("generated_applications.id"), nullable=False)

    contact_name = Column(Text)
    contact_title = Column(Text)
    contact_email = Column(Text)
    contact_linkedin = Column(Text)
    email_verified = Column(Boolean, default=False)
    verification_method = Column(Text)

    email_subject = Column(Text)
    email_body = Column(Text)
    email_html_body = Column(Text)
    email_sent_at = Column(TIMESTAMP(timezone=True))
    email_message_id = Column(Text)
    email_thread_id = Column(Text)

    status = Column(
        String(30),
        nullable=False,
        default="drafted",
    )

    company_context = Column(JSONB)
    send_error = Column(Text)
    follow_up_count = Column(Integer, default=0)
    last_follow_up_at = Column(TIMESTAMP(timezone=True))
    next_follow_up_at = Column(TIMESTAMP(timezone=True))
    notes = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
