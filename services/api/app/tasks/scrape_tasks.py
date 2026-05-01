import asyncio
import json
import re
from collections.abc import Coroutine
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from celery.exceptions import Retry
from pydantic import ValidationError
from redis import Redis
from supabase import create_client

from ..config import settings
from ..prompts import bulk_import
from ..schemas.shared import JobRequirements
from ..schemas.vault import BulkImportProposedNode
from ..services.bulk_import_store import set_import_preview, set_import_status
from ..services.matcher import (
    JobRequirementExtractionError,
    embed_job_requirements,
    extract_job_requirements,
    vector_to_pg_literal,
)
from ..services.scraper import ScrapeError, ScrapeResult, job_scraper
from .celery_app import app

logger = structlog.get_logger()

JOB_COLUMNS = """
    id,
    user_id,
    url,
    raw_html,
    raw_text,
    company_name,
    role_title,
    requirements::text AS requirements,
    (embedding IS NOT NULL) AS is_embedded,
    scraped_at,
    created_at
"""


class ResumeExtractionError(Exception):
    pass


class BulkImportParseError(Exception):
    pass


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def _pg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _connect_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if "localhost" not in url and "127.0.0.1" not in url:
        kwargs["ssl"] = "require"
    if ":6543/" in url:
        kwargs["statement_cache_size"] = 0
    return kwargs


async def _connect_jobs() -> asyncpg.Connection:
    url = settings.DATABASE_URL_POOLED
    return await asyncpg.connect(_pg_dsn(url), **_connect_kwargs(url))


def _redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _get_cached_scrape(url: str) -> str | None:
    try:
        cached = _redis().get(f"scrape:{url}")
    except Exception as exc:
        logger.warning("job_scrape_cache_read_failed", url=url, error=str(exc))
        return None
    return cached if isinstance(cached, str) and cached.strip() else None


def _cache_scrape(url: str, raw_text: str) -> None:
    try:
        _redis().setex(f"scrape:{url}", 3600, raw_text)
    except Exception as exc:
        logger.warning("job_scrape_cache_write_failed", url=url, error=str(exc))


async def get_job_for_processing(job_id: str | UUID) -> dict[str, Any] | None:
    conn = await _connect_jobs()
    try:
        row = await conn.fetchrow(
            f"""
            SELECT {JOB_COLUMNS}
            FROM job_descriptions
            WHERE id = $1
            """,
            UUID(str(job_id)),
        )
    finally:
        await conn.close()

    return dict(row) if row else None


async def _update_job_scrape_result(
    job_id: str | UUID,
    user_id: str | UUID,
    result: ScrapeResult,
) -> None:
    conn = await _connect_jobs()
    try:
        await conn.execute(
            """
            UPDATE job_descriptions
            SET raw_html = $3,
                raw_text = $4,
                scraped_at = $5
            WHERE id = $1 AND user_id = $2
            """,
            UUID(str(job_id)),
            UUID(str(user_id)),
            result.raw_html,
            result.raw_text,
            datetime.now(UTC),
        )
    finally:
        await conn.close()


async def _update_job_scrape_failure(
    job_id: str | UUID,
    user_id: str | UUID,
    message: str,
) -> None:
    conn = await _connect_jobs()
    try:
        await conn.execute(
            """
            UPDATE job_descriptions
            SET raw_text = $3
            WHERE id = $1 AND user_id = $2
            """,
            UUID(str(job_id)),
            UUID(str(user_id)),
            message,
        )
    finally:
        await conn.close()


async def _update_job_requirements_embedding(
    job_id: str | UUID,
    user_id: str | UUID,
    requirements: JobRequirements,
    embedding: list[float],
) -> None:
    conn = await _connect_jobs()
    try:
        await conn.execute(
            """
            UPDATE job_descriptions
            SET company_name = $3,
                role_title = $4,
                requirements = $5::jsonb,
                embedding = $6::vector
            WHERE id = $1 AND user_id = $2
            """,
            UUID(str(job_id)),
            UUID(str(user_id)),
            requirements.company_name,
            requirements.role_title,
            json.dumps(requirements.model_dump(mode="json")),
            vector_to_pg_literal(embedding),
        )
    finally:
        await conn.close()


def dispatch_scrape_job(job_id: str | UUID) -> None:
    scrape_job_task.apply_async(args=[str(job_id)], queue="heavy")


def dispatch_extract_and_embed_job(job_id: str | UUID) -> None:
    extract_and_embed_task.apply_async(args=[str(job_id)], queue="default")


@app.task(bind=True, max_retries=2, default_retry_delay=10, queue="heavy")  # type: ignore[untyped-decorator]
def scrape_job_task(self: Any, job_id: str) -> dict[str, Any] | None:
    job = _run(get_job_for_processing(job_id))
    if not job:
        return None

    url = job.get("url")
    if not isinstance(url, str) or not url.strip():
        return None

    user_id = UUID(str(job["user_id"]))
    try:
        cached_text = _get_cached_scrape(url)
        if cached_text:
            result = ScrapeResult(
                raw_html=str(job.get("raw_html") or ""),
                raw_text=cached_text,
                method="cache",
            )
        else:
            try:
                result = _run(job_scraper.scrape(url))
            except ScrapeError as exc:
                _run(_update_job_scrape_failure(job["id"], user_id, str(exc)))
                if exc.retryable and self.request.retries < 2:
                    countdown = 10 if self.request.retries == 0 else 30
                    raise self.retry(exc=exc, countdown=countdown)
                logger.warning(
                    "job_scrape_failed",
                    job_id=str(job_id),
                    user_id=str(user_id),
                    error=str(exc),
                )
                return {"status": "failed", "error_message": str(exc)}

            _cache_scrape(url, result.raw_text)

        _run(_update_job_scrape_result(job["id"], user_id, result))
        dispatch_extract_and_embed_job(job_id)
    except Retry:
        raise
    except Exception as exc:
        if self.request.retries < 2:
            countdown = 10 if self.request.retries == 0 else 30
            raise self.retry(exc=exc, countdown=countdown)
        logger.error(
            "job_scrape_task_failed",
            job_id=str(job_id),
            user_id=str(user_id),
            error=str(exc),
        )
        return {"status": "failed", "error_message": "Job scraping failed."}

    return {"status": "scraped", "method": result.method}


@app.task(bind=True, max_retries=2, default_retry_delay=5, queue="default")  # type: ignore[untyped-decorator]
def extract_and_embed_task(self: Any, job_id: str) -> dict[str, Any] | None:
    job = _run(get_job_for_processing(job_id))
    if not job:
        return None

    raw_text = job.get("raw_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None

    user_id = UUID(str(job["user_id"]))
    try:
        requirements = _run(extract_job_requirements(raw_text, user_id))
        embedding = _run(embed_job_requirements(requirements, user_id))
        _run(_update_job_requirements_embedding(job["id"], user_id, requirements, embedding))
    except JobRequirementExtractionError as exc:
        if self.request.retries < 1:
            raise self.retry(exc=exc, countdown=5)
        logger.warning(
            "job_requirements_extract_failed",
            job_id=str(job_id),
            user_id=str(user_id),
            error=str(exc),
        )
        return {"status": "failed", "error_message": str(exc)}
    except Exception as exc:
        if self.request.retries < 2:
            countdown = 5 if self.request.retries == 0 else 15
            raise self.retry(exc=exc, countdown=countdown)
        logger.error(
            "job_extract_embed_failed",
            job_id=str(job_id),
            user_id=str(user_id),
            error=str(exc),
        )
        return {"status": "failed", "error_message": "Job extraction failed."}

    return {"status": "embedded"}


def parse_bulk_nodes_response(raw: str) -> list[BulkImportProposedNode]:
    try:
        parsed = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        raise BulkImportParseError("Bulk import LLM response was not valid JSON") from exc

    if isinstance(parsed, dict) and isinstance(parsed.get("nodes"), list):
        parsed = parsed["nodes"]
    if not isinstance(parsed, list):
        raise BulkImportParseError("Bulk import LLM response must be a JSON array")

    nodes: list[BulkImportProposedNode] = []
    for item in parsed:
        try:
            nodes.append(BulkImportProposedNode.model_validate(item))
        except ValidationError as exc:
            raise BulkImportParseError("Bulk import LLM response had invalid node fields") from exc

    if not nodes:
        raise BulkImportParseError("No professional experiences found in this document.")
    return nodes


def _split_storage_path(storage_path: str) -> tuple[str, str]:
    normalized = storage_path.strip().lstrip("/")
    bucket_prefix = f"{settings.SUPABASE_RESUME_BUCKET}/"
    if normalized.startswith(bucket_prefix):
        return settings.SUPABASE_RESUME_BUCKET, normalized[len(bucket_prefix):]
    return settings.SUPABASE_RESUME_BUCKET, normalized


def _download_resume_pdf(storage_path: str) -> bytes:
    bucket, path = _split_storage_path(storage_path)
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    data = client.storage.from_(bucket).download(path)
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    raise ResumeExtractionError("Could not download resume PDF from storage.")


def extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ResumeExtractionError("PDF extraction dependency is not installed.") from exc

    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise ResumeExtractionError("Could not extract text from PDF.") from exc

    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        raise ResumeExtractionError("Could not extract text from PDF.")
    return cleaned


@app.task(bind=True, max_retries=1, queue="heavy")  # type: ignore[untyped-decorator]
def bulk_import_task(self: Any, user_id: str, storage_path: str) -> dict[str, Any]:
    task_id = self.request.id
    set_import_status(task_id, status="parsing", user_id=user_id, storage_path=storage_path)

    try:
        pdf_bytes = _download_resume_pdf(storage_path)
        resume_text = extract_pdf_text(pdf_bytes)
        from ..services.llm_client import llm_client

        raw_nodes = _run(
            llm_client.complete(
                system_prompt=bulk_import.SYSTEM_PROMPT,
                user_prompt=resume_text,
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                response_format="json",
                user_id=UUID(user_id),
                task_type="bulk_import",
                prompt_version=bulk_import.VERSION,
            )
        )
        nodes = parse_bulk_nodes_response(raw_nodes)
        serializable = [node.model_dump(mode="json") for node in nodes]
        set_import_preview(task_id, user_id=user_id, storage_path=storage_path, nodes=serializable)
        set_import_status(
            task_id,
            status="ready_to_review",
            user_id=user_id,
            storage_path=storage_path,
            total_nodes=len(nodes),
        )
    except ResumeExtractionError as exc:
        message = "Could not extract text from PDF."
        logger.warning("vault_bulk_import_pdf_failed", task_id=task_id, error=str(exc))
        set_import_status(
            task_id,
            status="failed",
            user_id=user_id,
            storage_path=storage_path,
            error_message=message,
        )
        return {"status": "failed", "error_message": message}
    except BulkImportParseError as exc:
        if self.request.retries < 1:
            raise self.retry(exc=exc, countdown=10)
        message = str(exc)
        logger.warning("vault_bulk_import_parse_failed", task_id=task_id, error=message)
        set_import_status(
            task_id,
            status="failed",
            user_id=user_id,
            storage_path=storage_path,
            error_message=message,
        )
        return {"status": "failed", "error_message": message}
    except Exception as exc:
        if self.request.retries < 1:
            raise self.retry(exc=exc, countdown=10)
        message = "Bulk import failed."
        logger.error("vault_bulk_import_failed", task_id=task_id, error=str(exc))
        set_import_status(
            task_id,
            status="failed",
            user_id=user_id,
            storage_path=storage_path,
            error_message=message,
        )
        return {"status": "failed", "error_message": message}

    return {"status": "ready_to_review", "total_nodes": len(nodes)}
