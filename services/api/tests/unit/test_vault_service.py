from datetime import UTC, datetime
from uuid import uuid4


def _node(**overrides):
    from app.schemas.vault import NodeResponse

    base = {
        "id": uuid4(),
        "title": "Distributed Cache",
        "organization": "Virginia Tech",
        "role": "Research Assistant",
        "start_date": None,
        "end_date": None,
        "description": "Designed a cache for HPC workloads.",
        "bullet_points": ["Reduced latency by 35%."],
        "node_type": "research",
        "tags": ["hpc"],
        "is_embedded": True,
        "source": "manual",
        "is_archived": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    base.update(overrides)
    return NodeResponse(**base)


def test_content_fields_changed_detects_description_change():
    from app.services.vault_service import content_fields_changed

    node = _node()
    assert content_fields_changed(node, {"description": "Built a new cache layer."}) is True


def test_content_fields_changed_ignores_date_only_change():
    from app.services.vault_service import content_fields_changed

    node = _node()
    assert content_fields_changed(node, {"start_date": "2024-01-01"}) is False


def test_bulk_import_dedupe_key_is_stable():
    from app.schemas.vault import NodeCreateRequest
    from app.services.vault_service import build_bulk_import_dedupe_key

    payload = NodeCreateRequest(
        title="Analytics Dashboard",
        description="Built a dashboard for operations teams.",
        bullet_points=["Cut report prep time by 30%."],
        node_type="project",
    )

    assert build_bulk_import_dedupe_key("u/resume.pdf", payload) == build_bulk_import_dedupe_key(
        "u/resume.pdf",
        payload,
    )


def test_row_to_experience_node_result_contract():
    from app.services.vault_service import row_to_experience_node_result

    row = {
        "id": uuid4(),
        "title": "Analytics Dashboard",
        "organization": "Acme",
        "role": "Engineer",
        "start_date": None,
        "end_date": None,
        "description": "Built a dashboard for operations teams.",
        "bullet_points": '["Cut report prep time by 30%."]',
        "node_type": "project",
        "tags": ["analytics"],
        "is_embedded": True,
        "source": "manual",
        "is_archived": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }

    result = row_to_experience_node_result(row, similarity_score=0.87)

    assert result.id == row["id"]
    assert result.bullet_points == ["Cut report prep time by 30%."]
    assert result.similarity_score == 0.87
