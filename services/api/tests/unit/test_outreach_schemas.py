"""Unit tests for Pydantic request/response schemas (app/schemas/outreach.py)."""
from uuid import uuid4

import pytest
from pydantic import ValidationError


class TestCampaignCreateRequest:
    def test_valid_email_accepted(self):
        from app.schemas.outreach import CampaignCreateRequest

        r = CampaignCreateRequest(application_id=uuid4(), contact_email="user@example.com")
        assert r.contact_email == "user@example.com"

    def test_email_with_subdomain_accepted(self):
        from app.schemas.outreach import CampaignCreateRequest

        r = CampaignCreateRequest(
            application_id=uuid4(), contact_email="user@mail.company.co.uk"
        )
        assert r.contact_email == "user@mail.company.co.uk"

    def test_email_with_plus_tag_accepted(self):
        from app.schemas.outreach import CampaignCreateRequest

        r = CampaignCreateRequest(application_id=uuid4(), contact_email="user+tag@example.com")
        assert r.contact_email == "user+tag@example.com"

    @pytest.mark.parametrize(
        "bad_email",
        ["not-an-email", "@nodomain.com", "user@", "plaintext", "user @example.com"],
    )
    def test_invalid_email_raises_validation_error(self, bad_email):
        from app.schemas.outreach import CampaignCreateRequest

        with pytest.raises(ValidationError):
            CampaignCreateRequest(application_id=uuid4(), contact_email=bad_email)

    def test_no_email_field_is_valid(self):
        from app.schemas.outreach import CampaignCreateRequest

        r = CampaignCreateRequest(application_id=uuid4())
        assert r.contact_email is None

    def test_auto_discover_defaults_to_true(self):
        from app.schemas.outreach import CampaignCreateRequest

        r = CampaignCreateRequest(application_id=uuid4())
        assert r.auto_discover_contact is True

    def test_all_optional_fields_default_to_none(self):
        from app.schemas.outreach import CampaignCreateRequest

        r = CampaignCreateRequest(application_id=uuid4())
        assert r.contact_name is None
        assert r.contact_title is None
        assert r.contact_linkedin is None


class TestCampaignUpdateRequest:
    @pytest.mark.parametrize(
        "status", ["drafted", "queued", "meeting_scheduled", "rejected", "archived"]
    )
    def test_valid_statuses_accepted(self, status):
        from app.schemas.outreach import CampaignUpdateRequest

        r = CampaignUpdateRequest(status=status)
        assert r.status == status

    @pytest.mark.parametrize("status", ["sent", "responded", "opened", "pending", "DRAFTED", ""])
    def test_non_user_settable_statuses_rejected(self, status):
        """'sent' and 'responded' are set by the system, not by users via PATCH."""
        from app.schemas.outreach import CampaignUpdateRequest

        with pytest.raises(ValidationError):
            CampaignUpdateRequest(status=status)

    def test_all_fields_optional(self):
        from app.schemas.outreach import CampaignUpdateRequest

        r = CampaignUpdateRequest()
        assert r.status is None
        assert r.contact_name is None
        assert r.contact_email is None
        assert r.contact_title is None
        assert r.notes is None


class TestDraftEmailRequest:
    def test_default_tone_is_conversational(self):
        from app.schemas.outreach import DraftEmailRequest

        assert DraftEmailRequest().tone == "conversational"

    def test_custom_tone_accepted(self):
        from app.schemas.outreach import DraftEmailRequest

        assert DraftEmailRequest(tone="bold").tone == "bold"


class TestSendEmailRequest:
    def test_defaults(self):
        from app.schemas.outreach import SendEmailRequest

        r = SendEmailRequest()
        assert r.provider == "gmail"
        assert r.attach_resume is True

    def test_outlook_provider(self):
        from app.schemas.outreach import SendEmailRequest

        r = SendEmailRequest(provider="outlook", attach_resume=False)
        assert r.provider == "outlook"
        assert r.attach_resume is False


class TestOAuthInitiateRequest:
    def test_return_to_optional(self):
        from app.schemas.outreach import OAuthInitiateRequest

        r = OAuthInitiateRequest()
        assert r.return_to is None

    def test_return_to_set(self):
        from app.schemas.outreach import OAuthInitiateRequest

        r = OAuthInitiateRequest(return_to="/outreach/campaigns/abc")
        assert r.return_to == "/outreach/campaigns/abc"
