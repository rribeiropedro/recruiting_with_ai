from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


NodeType = Literal[
    "work",
    "research",
    "project",
    "hackathon",
    "certification",
    "education",
    "leadership",
    "volunteer",
]
NodeSource = Literal["manual", "bulk_import"]


def _parse_partial_date(value: object) -> object:
    if value is None or isinstance(value, date):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) == 7:
            return date.fromisoformat(f"{trimmed}-01")
    return value


class _NodeDateValidation(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_partial_dates(cls, value: object) -> object:
        return _parse_partial_date(value)

    @model_validator(mode="after")
    def validate_date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class NodeCreateRequest(_NodeDateValidation):
    title: str = Field(..., min_length=1, max_length=200)
    organization: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=200)
    description: str = Field(..., min_length=10, max_length=2000)
    bullet_points: list[str] = Field(default_factory=list, max_length=10)
    node_type: NodeType


class NodeUpdateRequest(_NodeDateValidation):
    title: str | None = Field(None, min_length=1, max_length=200)
    organization: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=200)
    description: str | None = Field(None, min_length=10, max_length=2000)
    bullet_points: list[str] | None = Field(None, max_length=10)
    node_type: NodeType | None = None

    @model_validator(mode="after")
    def validate_non_nullable_updates(self):
        for field in ("title", "description", "bullet_points", "node_type"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class NodeResponse(BaseModel):
    id: UUID
    title: str
    organization: str | None
    role: str | None
    start_date: date | None
    end_date: date | None
    description: str
    bullet_points: list[str]
    node_type: NodeType
    tags: list[str]
    is_embedded: bool
    source: NodeSource
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class NodeListResponse(BaseModel):
    nodes: list[NodeResponse]
    total: int
    cursor: UUID | None


class BulkImportRequest(BaseModel):
    storage_path: str = Field(..., min_length=1, max_length=1024)


class BulkImportStartResponse(BaseModel):
    task_id: str


class BulkImportStatusResponse(BaseModel):
    task_id: str
    status: str
    nodes_created: int = 0
    total_nodes: int | None = None
    error_message: str | None = None


class BulkImportProposedNode(NodeCreateRequest):
    pass


class BulkImportPreviewResponse(BaseModel):
    task_id: str
    nodes: list[BulkImportProposedNode]


class BulkImportCommitRequest(BaseModel):
    nodes: list[BulkImportProposedNode] = Field(default_factory=list, max_length=100)


class BulkImportCommitResponse(BaseModel):
    task_id: str
    nodes_created: int
    nodes: list[NodeResponse]
