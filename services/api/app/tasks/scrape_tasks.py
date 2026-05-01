import asyncio
import json
import re
from collections.abc import Coroutine
from io import BytesIO
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from supabase import create_client

from ..config import settings
from ..prompts import bulk_import
from ..schemas.vault import BulkImportProposedNode
from ..services.bulk_import_store import set_import_preview, set_import_status
from .celery_app import app

logger = structlog.get_logger()

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
