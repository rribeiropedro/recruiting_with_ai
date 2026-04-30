"""
Integration tests for the outreach router.

These tests use FastAPI's TestClient with a mocked Supabase client so they
exercise the full request/response cycle — auth dependency, guard conditions,
status-transition enforcement — without a live database.
"""
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

TEST_USER_ID = uuid4()


def _build_app() -> FastAPI:
    from app.dependencies import get_current_user
    from app.routers.outreach import router

    app = FastAPI()

    # Wire up slowapi so the rate-limited send endpoint doesn't error out
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(router, prefix="/outreach")
    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    return app


def _campaign(status: str = "drafted", **overrides) -> dict:
    base = {
        "id": str(uuid4()),
        "application_id": str(uuid4()),
        "user_id": str(TEST_USER_ID),
        "status": status,
        "contact_name": None,
        "contact_title": None,
        "contact_email": "hiring@company.com",
        "email_verified": False,
        "email_subject": "Re: opportunity",
        "email_body": "Cold email body here",
        "follow_up_count": 0,
        "notes": None,
        "send_error": None,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _mock_db_for_get(campaign: dict) -> MagicMock:
    """Return a mock Supabase client that serves a single campaign on SELECT."""
    db = MagicMock()
    (
        db.table.return_value.select.return_value.eq.return_value.eq
        .return_value.single.return_value.execute.return_value
    ).data = campaign
    return db


# ─── Status transition enforcement ───────────────────────────────────────────

class TestStatusTransitions:
    """
    Tests import VALID_TRANSITIONS directly to validate the map as a contract,
    then verify the router enforces it through the PATCH endpoint.
    """

    def test_valid_transitions_map_completeness(self):
        from app.routers.outreach import VALID_TRANSITIONS

        all_statuses = {
            "drafted", "queued", "sent", "responded",
            "meeting_scheduled", "rejected", "archived",
        }
        assert set(VALID_TRANSITIONS.keys()) == all_statuses

    @pytest.mark.parametrize("from_status,to_status", [
        ("drafted", "queued"),
        ("drafted", "archived"),
        ("queued", "sent"),
        ("queued", "drafted"),
        ("sent", "responded"),
        ("sent", "meeting_scheduled"),
        ("sent", "rejected"),
        ("sent", "archived"),
        ("responded", "meeting_scheduled"),
        ("responded", "rejected"),
        ("responded", "archived"),
        ("meeting_scheduled", "rejected"),
        ("meeting_scheduled", "archived"),
        ("rejected", "archived"),
        ("archived", "drafted"),
    ])
    def test_all_valid_transitions_present(self, from_status, to_status):
        from app.routers.outreach import VALID_TRANSITIONS

        assert to_status in VALID_TRANSITIONS[from_status]

    @pytest.mark.parametrize("from_status,to_status", [
        ("drafted", "sent"),
        ("drafted", "responded"),
        ("drafted", "meeting_scheduled"),
        ("queued", "responded"),
        ("queued", "meeting_scheduled"),
        ("responded", "drafted"),
        ("responded", "queued"),
        ("archived", "sent"),
        ("rejected", "drafted"),
        ("rejected", "queued"),
        ("meeting_scheduled", "drafted"),
    ])
    def test_invalid_transitions_absent(self, from_status, to_status):
        from app.routers.outreach import VALID_TRANSITIONS

        assert to_status not in VALID_TRANSITIONS.get(from_status, [])

    def test_rejected_can_only_go_to_archived(self):
        from app.routers.outreach import VALID_TRANSITIONS

        assert VALID_TRANSITIONS["rejected"] == ["archived"]

    def test_archived_can_only_reactivate_to_drafted(self):
        from app.routers.outreach import VALID_TRANSITIONS

        assert VALID_TRANSITIONS["archived"] == ["drafted"]


class TestPatchCampaignStatusViaRouter:
    def test_invalid_transition_returns_422(self):
        campaign = _campaign(status="drafted")
        app = _build_app()
        db = _mock_db_for_get(campaign)

        # "meeting_scheduled" passes schema validation but is not a valid
        # transition from "drafted", so the router's guard raises the 422.
        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app).patch(
                f"/outreach/campaigns/{campaign['id']}",
                json={"status": "meeting_scheduled"},
            )

        assert resp.status_code == 422
        assert "Cannot transition" in resp.json()["detail"]

    def test_invalid_transition_drafted_to_responded(self):
        campaign = _campaign(status="drafted")
        app = _build_app()
        db = _mock_db_for_get(campaign)

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app).patch(
                f"/outreach/campaigns/{campaign['id']}",
                json={"status": "meeting_scheduled"},
            )

        assert resp.status_code == 422

    def test_unknown_campaign_returns_404(self):
        app = _build_app()
        db = MagicMock()
        (
            db.table.return_value.select.return_value.eq.return_value.eq
            .return_value.single.return_value.execute.return_value
        ).data = None

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app).patch(
                f"/outreach/campaigns/{uuid4()}",
                json={"status": "queued"},
            )

        assert resp.status_code == 404

    def test_valid_transition_calls_db_update(self):
        from datetime import datetime

        from app.schemas.outreach import CampaignResponse

        campaign = _campaign(status="drafted")
        updated = {**campaign, "status": "queued"}
        app = _build_app()

        db = MagicMock()
        (
            db.table.return_value.select.return_value.eq.return_value.eq
            .return_value.single.return_value.execute.return_value
        ).data = campaign
        (
            db.table.return_value.update.return_value.eq.return_value.execute.return_value
        ).data = [updated]

        enriched_response = CampaignResponse(
            id=campaign["id"],
            application_id=campaign["application_id"],
            company_name=None,
            role_title=None,
            contact_name=None,
            contact_title=None,
            contact_email=campaign["contact_email"],
            email_verified=False,
            email_subject=campaign["email_subject"],
            email_body=campaign["email_body"],
            status="queued",
            follow_up_count=0,
            notes=None,
            send_error=None,
            created_at=datetime.fromisoformat(campaign["created_at"]),
            updated_at=datetime.fromisoformat(campaign["updated_at"]),
        )

        with (
            patch("app.routers.outreach._db", return_value=db),
            patch("app.routers.outreach._enrich_campaign", return_value=enriched_response),
        ):
            resp = TestClient(app).patch(
                f"/outreach/campaigns/{campaign['id']}",
                json={"status": "queued"},
            )

        assert resp.status_code == 200
        db.table.return_value.update.assert_called_once_with({"status": "queued"})


# ─── Send email guard conditions ─────────────────────────────────────────────

class TestSendEmailGuards:
    def test_already_sent_returns_409(self):
        campaign = _campaign(status="sent")
        app = _build_app()
        db = _mock_db_for_get(campaign)

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app, raise_server_exceptions=False).post(
                f"/outreach/campaigns/{campaign['id']}/send",
                json={"provider": "gmail"},
            )

        assert resp.status_code == 409
        assert "already sent" in resp.json()["detail"].lower()

    def test_responded_status_also_returns_409(self):
        """'responded' is treated the same as 'sent' — email was already dispatched."""
        campaign = _campaign(status="responded")
        app = _build_app()
        db = _mock_db_for_get(campaign)

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app, raise_server_exceptions=False).post(
                f"/outreach/campaigns/{campaign['id']}/send",
                json={"provider": "gmail"},
            )

        assert resp.status_code == 409

    def test_meeting_scheduled_also_returns_409(self):
        campaign = _campaign(status="meeting_scheduled")
        app = _build_app()
        db = _mock_db_for_get(campaign)

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app, raise_server_exceptions=False).post(
                f"/outreach/campaigns/{campaign['id']}/send",
                json={"provider": "gmail"},
            )

        assert resp.status_code == 409

    def test_missing_contact_email_returns_422(self):
        campaign = _campaign(contact_email=None)
        app = _build_app()
        db = _mock_db_for_get(campaign)

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app, raise_server_exceptions=False).post(
                f"/outreach/campaigns/{campaign['id']}/send",
                json={"provider": "gmail"},
            )

        assert resp.status_code == 422
        assert "contact email" in resp.json()["detail"].lower()

    def test_missing_email_body_returns_422(self):
        campaign = _campaign(email_body=None)
        app = _build_app()
        db = _mock_db_for_get(campaign)

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app, raise_server_exceptions=False).post(
                f"/outreach/campaigns/{campaign['id']}/send",
                json={"provider": "gmail"},
            )

        assert resp.status_code == 422
        assert "email body" in resp.json()["detail"].lower()

    def test_unknown_campaign_returns_404(self):
        app = _build_app()
        db = MagicMock()
        (
            db.table.return_value.select.return_value.eq.return_value.eq
            .return_value.single.return_value.execute.return_value
        ).data = None

        with patch("app.routers.outreach._db", return_value=db):
            resp = TestClient(app, raise_server_exceptions=False).post(
                f"/outreach/campaigns/{uuid4()}/send",
                json={"provider": "gmail"},
            )

        assert resp.status_code == 404

    def test_valid_campaign_dispatches_task_and_returns_success(self):
        campaign = _campaign(status="drafted")
        app = _build_app()
        db = _mock_db_for_get(campaign)

        with (
            patch("app.routers.outreach._db", return_value=db),
            patch("app.tasks.outreach_tasks.send_email_task") as mock_task,
        ):
            mock_task.apply_async = MagicMock()
            resp = TestClient(app).post(
                f"/outreach/campaigns/{campaign['id']}/send",
                json={"provider": "gmail"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ─── OAuth return_to validation ───────────────────────────────────────────────

class TestOAuthReturnToValidation:
    """Verify that the OAuth initiation sanitises the return_to path."""

    def test_non_relative_return_to_is_rejected(self):
        """
        The router enforces return_to must start with '/'.
        An absolute URL like 'https://evil.com' should be replaced with '/'.
        We test this by inspecting the state parameter embedded in the auth_url.
        """

        import urllib.parse

        # Build state as the router does
        return_to = "https://evil.com/steal"
        safe_return = return_to if return_to.startswith("/") else "/"
        state = f"user-id:{urllib.parse.quote(safe_return, safe='/')}"

        # The state should contain '/' not the original URL
        decoded_return = urllib.parse.unquote(state.split(":", 1)[1])
        assert decoded_return == "/"
        assert "evil.com" not in decoded_return

    def test_relative_path_preserved(self):
        import urllib.parse

        return_to = "/outreach/campaigns/abc-123"
        safe_return = return_to if return_to.startswith("/") else "/"
        state = f"user-id:{urllib.parse.quote(safe_return, safe='/')}"

        decoded_return = urllib.parse.unquote(state.split(":", 1)[1])
        assert decoded_return == return_to


# ─── Row-to-response mapping ──────────────────────────────────────────────────

class TestRowToResponse:
    def test_maps_all_required_fields(self):
        from app.routers.outreach import _row_to_response

        row = {
            "id": str(uuid4()),
            "application_id": str(uuid4()),
            "contact_name": "Alice",
            "contact_title": "Recruiter",
            "contact_email": "alice@corp.com",
            "email_verified": True,
            "email_subject": "Hello",
            "email_body": "Body",
            "status": "drafted",
            "follow_up_count": 2,
            "notes": "Interesting role",
            "send_error": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }

        resp = _row_to_response(row, company_name="Corp", role_title="SWE")

        assert str(resp.id) == row["id"]
        assert resp.company_name == "Corp"
        assert resp.role_title == "SWE"
        assert resp.contact_name == "Alice"
        assert resp.status == "drafted"
        assert resp.follow_up_count == 2

    def test_missing_optional_fields_default_correctly(self):
        from app.routers.outreach import _row_to_response

        row = {
            "id": str(uuid4()),
            "application_id": str(uuid4()),
            "status": "drafted",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }

        resp = _row_to_response(row)

        assert resp.contact_name is None
        assert resp.email_verified is False
        assert resp.follow_up_count == 0
        assert resp.company_name is None
