from datetime import date

import pytest
from pydantic import ValidationError


class TestNodeCreateRequest:
    def test_valid_node_accepts_partial_month_dates(self):
        from app.schemas.vault import NodeCreateRequest

        node = NodeCreateRequest(
            title="Real-Time Analytics Dashboard",
            organization="Acme",
            role="Software Engineer",
            start_date="2024-01",
            end_date="2024-06",
            description="Built a dashboard for operational analytics.",
            bullet_points=["Reduced reporting latency by 40%."],
            node_type="project",
        )

        assert node.start_date == date(2024, 1, 1)
        assert node.end_date == date(2024, 6, 1)

    def test_invalid_node_type_rejected(self):
        from app.schemas.vault import NodeCreateRequest

        with pytest.raises(ValidationError):
            NodeCreateRequest(
                title="Bad node",
                description="This description is long enough.",
                bullet_points=[],
                node_type="award",
            )

    def test_end_date_before_start_date_rejected(self):
        from app.schemas.vault import NodeCreateRequest

        with pytest.raises(ValidationError):
            NodeCreateRequest(
                title="Bad dates",
                start_date="2024-06-01",
                end_date="2024-01-01",
                description="This description is long enough.",
                bullet_points=[],
                node_type="project",
            )


class TestNodeUpdateRequest:
    def test_date_only_update_is_valid(self):
        from app.schemas.vault import NodeUpdateRequest

        request = NodeUpdateRequest(start_date="2024-01")
        assert request.start_date == date(2024, 1, 1)

    @pytest.mark.parametrize("field", ["title", "description", "bullet_points", "node_type"])
    def test_non_nullable_fields_reject_explicit_null(self, field):
        from app.schemas.vault import NodeUpdateRequest

        with pytest.raises(ValidationError):
            NodeUpdateRequest(**{field: None})


class TestBulkImportSchemas:
    def test_proposed_node_uses_create_validation(self):
        from app.schemas.vault import BulkImportProposedNode

        node = BulkImportProposedNode(
            title="Distributed Cache",
            description="Built a cache for cluster workloads.",
            bullet_points=[],
            node_type="research",
        )

        assert node.node_type == "research"
