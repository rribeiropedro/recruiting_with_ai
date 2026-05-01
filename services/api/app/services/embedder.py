import json
from collections.abc import Mapping
from uuid import UUID


def _get_value(node: object, key: str) -> object:
    if isinstance(node, Mapping):
        return node.get(key)
    return getattr(node, key, None)


def _as_bullets(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value.strip() else []
        value = parsed
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def build_embedding_text(node: object) -> str:
    parts: list[str] = []

    title = _get_value(node, "title")
    organization = _get_value(node, "organization")
    role = _get_value(node, "role")
    description = _get_value(node, "description")
    bullet_points = _as_bullets(_get_value(node, "bullet_points"))

    if isinstance(title, str) and title.strip():
        parts.append(title.strip())
    if isinstance(organization, str) and organization.strip():
        parts.append(f"at {organization.strip()}")
    if isinstance(role, str) and role.strip():
        parts.append(f"as {role.strip()}")
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    parts.extend(bullet_points)

    return " | ".join(parts)


async def embed_node_text(node: object, user_id: UUID | None = None) -> list[float]:
    from .llm_client import llm_client

    return await llm_client.embed(build_embedding_text(node), user_id=user_id)
