from datetime import datetime
from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.types import UserDefinedType

from .base import Base


class Vector(UserDefinedType[list[float]]):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_kwargs: object) -> str:
        return f"vector({self.dimensions})"


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
    )

    url = Column(Text)
    raw_html = Column(Text)
    raw_text = Column(Text, nullable=False)

    company_name = Column(Text)
    role_title = Column(Text)
    requirements = Column(JSONB, nullable=False, default=dict)
    embedding = Column(Vector(1536))

    status = Column(String(30), nullable=False, default="pending")
    error_message = Column(Text)
    celery_task_id = Column(Text)

    scraped_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    @property
    def is_embedded(self) -> bool:
        return self.embedding is not None
