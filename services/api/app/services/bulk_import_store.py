import json
from typing import Any

import redis

from ..config import settings

PREVIEW_TTL_SECONDS = 30 * 60


def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _status_key(task_id: str) -> str:
    return f"vault:bulk_import:{task_id}:status"


def _preview_key(task_id: str) -> str:
    return f"vault:bulk_import:{task_id}:preview"


def set_import_status(
    task_id: str,
    *,
    status: str,
    user_id: str | None = None,
    storage_path: str | None = None,
    nodes_created: int = 0,
    total_nodes: int | None = None,
    error_message: str | None = None,
) -> None:
    payload = {
        "task_id": task_id,
        "status": status,
        "user_id": user_id,
        "storage_path": storage_path,
        "nodes_created": nodes_created,
        "total_nodes": total_nodes,
        "error_message": error_message,
    }
    _client().setex(_status_key(task_id), PREVIEW_TTL_SECONDS, json.dumps(payload))


def get_import_status(task_id: str) -> dict[str, Any] | None:
    raw = _client().get(_status_key(task_id))
    return json.loads(raw) if raw else None


def set_import_preview(
    task_id: str,
    *,
    user_id: str,
    storage_path: str,
    nodes: list[dict[str, Any]],
) -> None:
    payload = {"task_id": task_id, "user_id": user_id, "storage_path": storage_path, "nodes": nodes}
    client = _client()
    client.setex(_preview_key(task_id), PREVIEW_TTL_SECONDS, json.dumps(payload, default=str))


def get_import_preview(task_id: str) -> dict[str, Any] | None:
    raw = _client().get(_preview_key(task_id))
    return json.loads(raw) if raw else None
