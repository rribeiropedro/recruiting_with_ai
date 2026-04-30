import asyncio
import json
import re

import structlog
from celery import chain

from ..prompts import tag_node
from ..services.embedder import build_embedding_text, embed_node_text
from ..services.vault_service import (
    get_node_for_processing,
    update_node_embedding,
    update_node_tags,
)
from .celery_app import app

logger = structlog.get_logger()


def _run(coro):
    return asyncio.run(coro)


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    return fenced.group(1).strip() if fenced else text


def parse_tags_response(raw: str) -> list[str]:
    parsed = json.loads(_strip_json_fence(raw))
    if isinstance(parsed, dict) and isinstance(parsed.get("tags"), list):
        parsed = parsed["tags"]
    if not isinstance(parsed, list):
        raise ValueError("Tag response must be a JSON array")

    tags: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            raise ValueError("Tag response contains a non-string tag")
        tag = item.strip().lower().replace(" ", "-")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags[:15]


def dispatch_node_processing(node_id: str) -> None:
    try:
        chain(tag_node_task.si(str(node_id)), embed_node_task.si(str(node_id))).apply_async()
    except Exception as exc:
        logger.error("vault_node_processing_dispatch_failed", node_id=str(node_id), error=str(exc))


@app.task(bind=True, max_retries=3, default_retry_delay=5, queue="default")
def tag_node_task(self, node_id: str):
    node = _run(get_node_for_processing(node_id))
    if not node:
        return None

    try:
        from ..services.llm_client import llm_client

        raw_tags = _run(
            llm_client.complete(
                system_prompt=tag_node.SYSTEM_PROMPT,
                user_prompt=build_embedding_text(node),
                model="claude-haiku-4-5-20251001",
                response_format="json",
                user_id=node["user_id"],
                task_type="tag",
                prompt_version=tag_node.VERSION,
            )
        )
        tags = parse_tags_response(raw_tags)
    except ValueError as exc:
        if self.request.retries < 1:
            raise self.retry(exc=exc, countdown=5)
        tags = []
    except Exception as exc:
        countdown = 5 * (3 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)

    _run(update_node_tags(node_id, tags))
    return tags


@app.task(bind=True, max_retries=3, default_retry_delay=10, queue="default")
def embed_node_task(self, node_id: str):
    node = _run(get_node_for_processing(node_id))
    if not node:
        return None

    try:
        embedding = _run(embed_node_text(node, user_id=node["user_id"]))
        _run(update_node_embedding(node_id, embedding))
    except Exception as exc:
        countdown = 10 * (3 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)

    return True
