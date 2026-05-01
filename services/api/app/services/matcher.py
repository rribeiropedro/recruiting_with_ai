from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import ValidationError

from ..config import settings
from ..prompts import extract_requirements
from ..schemas.shared import ExperienceNodeResult, JobRequirements

LOW_RELEVANCE_THRESHOLD = 0.3
DEFAULT_TOP_K = 5


class JobRequirementExtractionError(Exception):
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


def vector_to_pg_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in embedding) + "]"


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value).strip() or None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        return []

    values: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        normalized = stripped.casefold()
        if not stripped or normalized in seen:
            continue
        seen.add(normalized)
        values.append(stripped)
    return values


def _experience_years(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def _normalize_requirements_payload(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "company_name": _string_or_none(payload.get("company_name")),
        "role_title": _string_or_none(payload.get("role_title")),
        "technical_skills": _string_list(payload.get("technical_skills")),
        "soft_skills": _string_list(payload.get("soft_skills")),
        "responsibilities": _string_list(payload.get("responsibilities")),
        "experience_years": _experience_years(payload.get("experience_years")),
        "education": _string_or_none(payload.get("education")),
        "nice_to_haves": _string_list(payload.get("nice_to_haves")),
        "industry": _string_or_none(payload.get("industry")),
    }


def parse_job_requirements_response(raw: str) -> JobRequirements:
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        message = "Requirements extraction response was not JSON"
        raise JobRequirementExtractionError(message) from exc

    if not isinstance(parsed, dict):
        message = "Requirements extraction response must be a JSON object"
        raise JobRequirementExtractionError(message)

    try:
        return JobRequirements.model_validate(_normalize_requirements_payload(parsed))
    except ValidationError as exc:
        message = "Requirements extraction response had invalid fields"
        raise JobRequirementExtractionError(message) from exc


def build_job_embedding_text(requirements: JobRequirements) -> str:
    parts: list[str] = []

    if requirements.role_title:
        parts.append(requirements.role_title)
    parts.extend(requirements.technical_skills)
    parts.extend(requirements.responsibilities[:5])
    if requirements.education:
        parts.append(requirements.education)
    parts.extend(requirements.nice_to_haves[:3])

    return " | ".join(part.strip() for part in parts if part.strip())


async def extract_job_requirements(raw_text: str, user_id: UUID) -> JobRequirements:
    from .llm_client import llm_client

    raw_requirements = await llm_client.complete(
        system_prompt=extract_requirements.SYSTEM_PROMPT,
        user_prompt=raw_text,
        model="claude-sonnet-4-20250514",
        response_format="json",
        user_id=user_id,
        task_type="extract",
        prompt_version=extract_requirements.VERSION,
    )
    return parse_job_requirements_response(raw_requirements)


async def embed_job_requirements(requirements: JobRequirements, user_id: UUID) -> list[float]:
    from .llm_client import llm_client

    embedding_text = build_job_embedding_text(requirements)
    return await llm_client.embed(embedding_text, user_id=user_id)


def has_low_relevance(results: list[ExperienceNodeResult]) -> bool:
    return not results or results[0].similarity_score < LOW_RELEVANCE_THRESHOLD


class SemanticMatcher:
    async def find_similar_nodes(
        self,
        embedding: list[float],
        user_id: UUID,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[ExperienceNodeResult]:
        if top_k <= 0 or not embedding:
            return []

        limit = min(top_k, 50)
        conn = await _connect()
        try:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    title,
                    organization,
                    role,
                    start_date,
                    end_date,
                    description,
                    bullet_points::text AS bullet_points,
                    node_type,
                    COALESCE(tags, ARRAY[]::text[]) AS tags,
                    1 - (embedding <=> $2::vector) AS similarity_score
                FROM experience_nodes
                WHERE user_id = $1
                  AND is_archived = FALSE
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> $2::vector
                LIMIT $3
                """,
                user_id,
                vector_to_pg_literal(embedding),
                limit,
            )
        finally:
            await conn.close()

        return [_row_to_experience_node_result(row) for row in rows]


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _row_to_experience_node_result(row: asyncpg.Record | Mapping[str, Any]) -> ExperienceNodeResult:
    data = dict(row)
    return ExperienceNodeResult(
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
        similarity_score=float(data["similarity_score"]),
    )


semantic_matcher = SemanticMatcher()
