from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from redis import Redis

from ..config import settings
from ..schemas.jobs import JobDescriptionResponse, JobSubmitRequest, MatchResult
from ..schemas.shared import JobRequirements
from .matcher import DEFAULT_TOP_K, has_low_relevance, semantic_matcher

logger = structlog.get_logger()

JOB_RESPONSE_COLUMNS = """
    id,
    url,
    company_name,
    role_title,
    requirements::text AS requirements,
    (embedding IS NOT NULL) AS is_embedded,
    status,
    error_message,
    created_at,
    updated_at
"""


class JobNotFound(Exception):
    pass


class JobNotReady(Exception):
    pass


class JobDispatchError(Exception):
    pass


def _pg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _connect_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if "localhost" not in url and "127.0.0.1" not in url:
        kwargs["ssl"] = "require"
    if ":6543/" in url:
        kwargs["statement_cache_size"] = 0
    return kwargs


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(
        _pg_dsn(settings.DATABASE_URL),
        **_connect_kwargs(settings.DATABASE_URL),
    )


def _redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _requirements(value: object) -> JobRequirements:
    if value is None:
        return JobRequirements()
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return JobRequirements()
    if isinstance(value, dict):
        return JobRequirements.model_validate(value)
    return JobRequirements()


def _row_to_response(row: asyncpg.Record | dict[str, Any]) -> JobDescriptionResponse:
    data = dict(row)
    return JobDescriptionResponse(
        id=data["id"],
        url=data.get("url"),
        company_name=data.get("company_name"),
        role_title=data.get("role_title"),
        requirements=_requirements(data.get("requirements")),
        is_embedded=bool(data.get("is_embedded")),
        status=data.get("status") or "pending",
        error_message=data.get("error_message"),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def _parse_vector(value: object) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str):
        return [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", value)]
    return []


def _get_cached_scrape(url: str) -> str | None:
    try:
        cached = _redis().get(f"scrape:{url}")
    except Exception as exc:
        logger.warning("job_scrape_cache_read_failed", url=url, error=str(exc))
        return None
    return cached if isinstance(cached, str) and cached.strip() else None


async def _set_celery_task_id(user_id: UUID, job_id: UUID, task_id: str) -> JobDescriptionResponse:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            f"""
            UPDATE job_descriptions
            SET celery_task_id = $3
            WHERE id = $1 AND user_id = $2
            RETURNING {JOB_RESPONSE_COLUMNS}
            """,
            job_id,
            user_id,
            task_id,
        )
    finally:
        await conn.close()
    if not row:
        raise JobNotFound
    return _row_to_response(row)


async def _find_recent_url_job(user_id: UUID, url: str) -> JobDescriptionResponse | None:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            f"""
            SELECT {JOB_RESPONSE_COLUMNS}
            FROM job_descriptions
            WHERE user_id = $1
              AND url = $2
              AND created_at >= NOW() - INTERVAL '1 hour'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id,
            url,
        )
    finally:
        await conn.close()
    return _row_to_response(row) if row else None


async def _insert_job(
    user_id: UUID,
    *,
    url: str | None,
    raw_text: str,
    status: str = "pending",
) -> JobDescriptionResponse:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            f"""
            INSERT INTO job_descriptions (user_id, url, raw_text, status)
            VALUES ($1, $2, $3, $4)
            RETURNING {JOB_RESPONSE_COLUMNS}
            """,
            user_id,
            url,
            raw_text,
            status,
        )
    finally:
        await conn.close()
    return _row_to_response(row)


async def submit_job(user_id: UUID, payload: JobSubmitRequest) -> JobDescriptionResponse:
    from ..tasks.scrape_tasks import dispatch_extract_and_embed_job, dispatch_scrape_job

    if payload.url:
        recent = await _find_recent_url_job(user_id, payload.url)
        if recent:
            return recent

        cached_text = _get_cached_scrape(payload.url)
        job = await _insert_job(user_id, url=payload.url, raw_text=cached_text or "")
        dispatch = dispatch_extract_and_embed_job if cached_text else dispatch_scrape_job
    else:
        job = await _insert_job(user_id, url=None, raw_text=payload.raw_text or "")
        dispatch = dispatch_extract_and_embed_job

    try:
        task_id = dispatch(job.id)
    except Exception as exc:
        logger.error(
            "job_task_dispatch_failed",
            job_id=str(job.id),
            user_id=str(user_id),
            error=str(exc),
        )
        raise JobDispatchError from exc

    return await _set_celery_task_id(user_id, job.id, task_id)


async def get_job(user_id: UUID, job_id: UUID) -> JobDescriptionResponse | None:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            f"""
            SELECT {JOB_RESPONSE_COLUMNS}
            FROM job_descriptions
            WHERE id = $1 AND user_id = $2
            """,
            job_id,
            user_id,
        )
    finally:
        await conn.close()
    return _row_to_response(row) if row else None


async def match_job(
    user_id: UUID,
    job_id: UUID,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> MatchResult:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """
            SELECT
                id,
                requirements::text AS requirements,
                embedding::text AS embedding
            FROM job_descriptions
            WHERE id = $1 AND user_id = $2
            """,
            job_id,
            user_id,
        )
    finally:
        await conn.close()

    if not row:
        raise JobNotFound

    embedding = _parse_vector(row["embedding"])
    if not embedding:
        raise JobNotReady

    requirements = _requirements(row["requirements"])
    matched_nodes = await semantic_matcher.find_similar_nodes(
        embedding=embedding,
        user_id=user_id,
        top_k=top_k,
    )
    return MatchResult(
        job_description_id=row["id"],
        job_requirements=requirements,
        matched_nodes=matched_nodes,
        low_relevance_warning=has_low_relevance(matched_nodes),
    )
