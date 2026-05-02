from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, Column, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from .base import Base
from .jobs import Vector


class GeneratedApplication(Base):
    __tablename__ = "generated_applications"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
    )
    job_description_id = Column(
        PGUUID(as_uuid=True), ForeignKey("job_descriptions.id"), nullable=False
    )

    matched_node_ids: Any = Column(ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list)
    similarity_scores: Any = Column(ARRAY(Float), nullable=False, default=list)
    tailored_content = Column(JSONB, nullable=False, default=dict)

    pdf_storage_path = Column(Text)
    pdf_url = Column(Text)
    resume_text = Column(Text)
    resume_embedding = Column(Vector(1536))
    job_embedding_snapshot = Column(Vector(1536))
    resume_summary = Column(Text)

    cache_hit = Column(Boolean, default=False)
    cache_source_id = Column(PGUUID(as_uuid=True), ForeignKey("generated_applications.id"))

    status = Column(String(30), nullable=False, default="pending")
    error_message = Column(Text)
    celery_task_id = Column(Text)

    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    completed_at = Column(TIMESTAMP(timezone=True))
