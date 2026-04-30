import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from ..config import settings
from ..schemas.shared import ExperienceNodeResult
from ..schemas.vault import NodeCreateRequest, NodeListResponse, NodeResponse, NodeUpdateRequest


CONTENT_FIELDS = {"title", "organization", "role", "description", "bullet_points"}

NODE_COLUMNS = """
    id,
    user_id,
    title,
    organization,
    role,
    start_date,
    end_date,
    description,
    bullet_points::text AS bullet_points,
    node_type,
    COALESCE(tags, ARRAY[]::text[]) AS tags,
    (embedding IS NOT NULL) AS is_embedded,
    source,
    is_archived,
    metadata::text AS metadata,
    created_at,
    updated_at
"""


class DuplicateBulkImportNode(Exception):
    pass


@dataclass(frozen=True)
class NodeUpdateResult:
    node: NodeResponse
    reprocess: bool


def _pg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _connect_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if "localhost" not in url and "127.0.0.1" not in url:
        kwargs["ssl"] = "require"
    if ":6543/" in url:
        kwargs["statement_cache_size"] = 0
    return kwargs


async def _connect(pooler: bool = False) -> asyncpg.Connection:
    url = settings.DATABASE_URL_POOLED if pooler else settings.DATABASE_URL
    return await asyncpg.connect(_pg_dsn(url), **_connect_kwargs(url))


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _row_to_response(row: asyncpg.Record | dict[str, Any]) -> NodeResponse:
    data = dict(row)
    return NodeResponse(
        id=data["id"],
        title=data["title"],
        organization=data.get("organization"),
        role=data.get("role"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        description=data["description"],
        bullet_points=_json_list(data.get("bullet_points")),
        node_type=data["node_type"],
        tags=list(data.get("tags") or []),
        is_embedded=bool(data.get("is_embedded")),
        source=data.get("source") or "manual",
        is_archived=bool(data.get("is_archived")),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def row_to_experience_node_result(
    row: asyncpg.Record | dict[str, Any],
    similarity_score: float,
) -> ExperienceNodeResult:
    node = _row_to_response(row)
    return ExperienceNodeResult(
        id=node.id,
        title=node.title,
        organization=node.organization,
        role=node.role,
        start_date=node.start_date,
        end_date=node.end_date,
        description=node.description,
        bullet_points=node.bullet_points,
        node_type=node.node_type,
        tags=node.tags,
        similarity_score=similarity_score,
    )


def build_bulk_import_dedupe_key(storage_path: str, node: NodeCreateRequest) -> str:
    payload = {
        "storage_path": storage_path,
        "title": node.title,
        "organization": node.organization,
        "role": node.role,
        "description": node.description,
        "bullet_points": node.bullet_points,
        "node_type": node.node_type,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalise_for_compare(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [item.strip() if isinstance(item, str) else item for item in value]
    return value


def content_fields_changed(existing: NodeResponse, updates: dict[str, Any]) -> bool:
    for field in CONTENT_FIELDS.intersection(updates):
        existing_value = _normalise_for_compare(getattr(existing, field))
        updated_value = _normalise_for_compare(updates[field])
        if existing_value != updated_value:
            return True
    return False


def vector_to_pg_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in embedding) + "]"


async def create_node(
    user_id: UUID,
    payload: NodeCreateRequest,
    *,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
) -> NodeResponse:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO experience_nodes (
                user_id, title, organization, role, start_date, end_date,
                description, bullet_points, node_type, tags, embedding,
                source, metadata, is_archived
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8::jsonb, $9, ARRAY[]::text[], NULL,
                $10, $11::jsonb, FALSE
            )
            RETURNING {NODE_COLUMNS}
            """,
            user_id,
            payload.title,
            payload.organization,
            payload.role,
            payload.start_date,
            payload.end_date,
            payload.description,
            json.dumps(payload.bullet_points),
            payload.node_type,
            source,
            json.dumps(metadata or {}),
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateBulkImportNode from exc
    finally:
        await conn.close()

    return _row_to_response(row)


async def get_node(user_id: UUID, node_id: UUID) -> NodeResponse | None:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            f"""
            SELECT {NODE_COLUMNS}
            FROM experience_nodes
            WHERE id = $1 AND user_id = $2
            """,
            node_id,
            user_id,
        )
    finally:
        await conn.close()
    return _row_to_response(row) if row else None


async def get_node_for_processing(node_id: str | UUID) -> dict[str, Any] | None:
    conn = await _connect(pooler=True)
    try:
        row = await conn.fetchrow(
            f"""
            SELECT {NODE_COLUMNS}
            FROM experience_nodes
            WHERE id = $1 AND is_archived = FALSE
            """,
            UUID(str(node_id)),
        )
    finally:
        await conn.close()
    if not row:
        return None
    data = dict(row)
    data["bullet_points"] = _json_list(data.get("bullet_points"))
    return data


async def list_nodes(
    user_id: UUID,
    *,
    node_type: str | None = None,
    search: str | None = None,
    cursor: UUID | None = None,
    limit: int = 20,
) -> NodeListResponse:
    page_size = max(1, min(limit, 50))
    where = ["user_id = $1", "is_archived = FALSE"]
    args: list[Any] = [user_id]

    if node_type:
        args.append(node_type)
        where.append(f"node_type = ${len(args)}")

    if search:
        args.append(f"%{search.strip()}%")
        placeholder = f"${len(args)}"
        where.append(
            f"""(
                title ILIKE {placeholder}
                OR description ILIKE {placeholder}
                OR EXISTS (
                    SELECT 1
                    FROM unnest(COALESCE(tags, ARRAY[]::text[])) AS tag
                    WHERE tag ILIKE {placeholder}
                )
            )"""
        )

    count_where = " AND ".join(where)
    page_where = list(where)
    page_args = list(args)
    if cursor:
        page_args.append(cursor)
        page_where.append(
            f"""created_at < (
                SELECT created_at
                FROM experience_nodes
                WHERE id = ${len(page_args)} AND user_id = $1
            )"""
        )

    page_args.append(page_size + 1)
    limit_placeholder = f"${len(page_args)}"

    conn = await _connect()
    try:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM experience_nodes WHERE {count_where}",
            *args,
        )
        rows = await conn.fetch(
            f"""
            SELECT {NODE_COLUMNS}
            FROM experience_nodes
            WHERE {" AND ".join(page_where)}
            ORDER BY created_at DESC, id DESC
            LIMIT {limit_placeholder}
            """,
            *page_args,
        )
    finally:
        await conn.close()

    has_more = len(rows) > page_size
    visible_rows = rows[:page_size]
    next_cursor = visible_rows[-1]["id"] if has_more and visible_rows else None
    return NodeListResponse(
        nodes=[_row_to_response(row) for row in visible_rows],
        total=int(total or 0),
        cursor=next_cursor,
    )


async def update_node(
    user_id: UUID,
    node_id: UUID,
    payload: NodeUpdateRequest,
) -> NodeUpdateResult | None:
    conn = await _connect()
    try:
        existing_row = await conn.fetchrow(
            f"""
            SELECT {NODE_COLUMNS}
            FROM experience_nodes
            WHERE id = $1 AND user_id = $2
            """,
            node_id,
            user_id,
        )
        if not existing_row:
            return None

        existing = _row_to_response(existing_row)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return NodeUpdateResult(node=existing, reprocess=False)

        reprocess = content_fields_changed(existing, updates)
        args: list[Any] = [node_id, user_id]
        sets: list[str] = []
        for field, value in updates.items():
            args.append(json.dumps(value) if field == "bullet_points" else value)
            cast = "::jsonb" if field == "bullet_points" else ""
            sets.append(f"{field} = ${len(args)}{cast}")

        if reprocess:
            sets.append("tags = ARRAY[]::text[]")
            sets.append("embedding = NULL")

        row = await conn.fetchrow(
            f"""
            UPDATE experience_nodes
            SET {", ".join(sets)}
            WHERE id = $1 AND user_id = $2
            RETURNING {NODE_COLUMNS}
            """,
            *args,
        )
    finally:
        await conn.close()

    return NodeUpdateResult(node=_row_to_response(row), reprocess=reprocess)


async def archive_node(user_id: UUID, node_id: UUID) -> bool:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """
            UPDATE experience_nodes
            SET is_archived = TRUE
            WHERE id = $1 AND user_id = $2
            RETURNING id
            """,
            node_id,
            user_id,
        )
    finally:
        await conn.close()
    return row is not None


async def update_node_tags(node_id: str | UUID, tags: list[str]) -> None:
    conn = await _connect(pooler=True)
    try:
        await conn.execute(
            """
            UPDATE experience_nodes
            SET tags = $2::text[]
            WHERE id = $1 AND is_archived = FALSE
            """,
            UUID(str(node_id)),
            tags,
        )
    finally:
        await conn.close()


async def update_node_embedding(node_id: str | UUID, embedding: list[float]) -> None:
    conn = await _connect(pooler=True)
    try:
        await conn.execute(
            """
            UPDATE experience_nodes
            SET embedding = $2::vector
            WHERE id = $1 AND is_archived = FALSE
            """,
            UUID(str(node_id)),
            vector_to_pg_literal(embedding),
        )
    finally:
        await conn.close()


async def matcher_eligible_node_ids(user_id: UUID) -> list[UUID]:
    conn = await _connect()
    try:
        rows = await conn.fetch(
            """
            SELECT id
            FROM experience_nodes
            WHERE user_id = $1
              AND is_archived = FALSE
              AND embedding IS NOT NULL
            ORDER BY created_at DESC
            """,
            user_id,
        )
    finally:
        await conn.close()
    return [row["id"] for row in rows]
