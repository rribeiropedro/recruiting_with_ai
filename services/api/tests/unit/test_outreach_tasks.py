"""Unit tests for outreach Celery tasks (app/tasks/outreach_tasks.py).

Tasks are tested via task.run() rather than task.apply() to avoid Celery
broker/result-backend connections — run() calls the function body directly
with the task object as self, bypassing all transport infrastructure.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

def _campaign(**overrides) -> dict:
    base = {
        "id": "camp-1",
        "application_id": "app-1",
        "user_id": "user-1",
        "status": "queued",
        "contact_name": "Alice",
        "contact_title": "Recruiter",
        "contact_email": "alice@corp.com",
        "contact_linkedin": None,
        "email_verified": False,
        "verification_method": None,
        "email_subject": "Re: opportunity",
        "email_body": "Cold email body",
        "email_message_id": None,
        "email_thread_id": None,
    }
    base.update(overrides)
    return base


def _app() -> dict:
    return {
        "id": "app-1",
        "job_description_id": "job-1",
        "resume_text_summary": "5 years Python",
        "pdf_storage_path": None,
    }


def _job() -> dict:
    return {
        "id": "job-1",
        "company_name": "Acme Corp",
        "role_title": "Software Engineer",
        "industry": "saas",
    }


def _profile() -> dict:
    return {
        "user_id": "user-1",
        "email": "sender@example.com",
        "full_name": "John Smith",
        "gmail_oauth_token": "encrypted-token",
        "outlook_oauth_token": None,
    }


def _make_db(campaign=None, app_data=None, job=None, profile=None) -> MagicMock:
    """Supabase mock that returns per-table data and exposes table mocks for assertions."""
    rows = {
        "outreach_campaigns": campaign,
        "generated_applications": app_data,
        "job_descriptions": job,
        "user_profiles": profile,
    }
    table_mocks: dict[str, MagicMock] = {}

    def _get_table(name: str) -> MagicMock:
        if name not in table_mocks:
            m = MagicMock()
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = rows.get(name)
            m.update.return_value.eq.return_value.execute.return_value.data = None
            table_mocks[name] = m
        return table_mocks[name]

    db = MagicMock()
    db.table.side_effect = _get_table
    db._mocks = table_mocks
    return db


# ── send_email_task ───────────────────────────────────────────────────────────

class TestSendEmailTask:
    """
    send_email_task has max_retries=0 — preventing duplicate sends is the
    primary constraint.  Tests call task.run() to execute the body directly.
    """

    def _run(
        self,
        campaign: dict,
        *,
        provider: str = "gmail",
        attach_resume: bool = False,
        send_result=None,
    ) -> MagicMock:
        from app.tasks.outreach_tasks import send_email_task
        from app.services.email_sender import SendResult, email_sender

        db = _make_db(campaign=campaign, profile=_profile(), app_data=_app())
        result = send_result or SendResult(success=True, message_id="msg-1", thread_id="t-1")

        with (
            patch("app.tasks.outreach_tasks._db", return_value=db),
            patch.object(email_sender, "send_gmail", new=AsyncMock(return_value=result)),
            patch.object(email_sender, "send_outlook", new=AsyncMock(return_value=result)),
        ):
            send_email_task.run(campaign["id"], provider=provider, attach_resume=attach_resume)

        return db

    def test_already_sent_skips_entirely(self):
        db = self._run(_campaign(status="sent"))
        db._mocks["outreach_campaigns"].update.assert_not_called()

    def test_responded_skips_entirely(self):
        db = self._run(_campaign(status="responded"))
        db._mocks["outreach_campaigns"].update.assert_not_called()

    def test_meeting_scheduled_skips_entirely(self):
        db = self._run(_campaign(status="meeting_scheduled"))
        db._mocks["outreach_campaigns"].update.assert_not_called()

    def test_missing_contact_email_reverts_to_drafted(self):
        db = self._run(_campaign(contact_email=None))
        db._mocks["outreach_campaigns"].update.assert_called_once_with({"status": "drafted"})

    def test_missing_email_body_reverts_to_drafted(self):
        db = self._run(_campaign(email_body=None))
        db._mocks["outreach_campaigns"].update.assert_called_once_with({"status": "drafted"})

    def test_successful_send_marks_sent_with_message_ids(self):
        from app.services.email_sender import SendResult

        result = SendResult(success=True, message_id="msg-abc", thread_id="thread-xyz")
        db = self._run(_campaign(), send_result=result)

        payload = db._mocks["outreach_campaigns"].update.call_args[0][0]
        assert payload["status"] == "sent"
        assert payload["email_message_id"] == "msg-abc"
        assert payload["email_thread_id"] == "thread-xyz"
        assert payload["send_error"] is None
        assert "email_sent_at" in payload

    def test_failed_send_reverts_to_drafted_and_records_error(self):
        from app.services.email_sender import SendResult

        result = SendResult(success=False, error="send_failed:smtp timeout")
        db = self._run(_campaign(), send_result=result)

        payload = db._mocks["outreach_campaigns"].update.call_args[0][0]
        assert payload["status"] == "drafted"
        assert payload["send_error"] == "send_failed:smtp timeout"

    def test_token_expired_reverts_to_drafted(self):
        from app.services.email_sender import SendResult

        result = SendResult(success=False, error="token_expired")
        db = self._run(_campaign(), send_result=result)

        payload = db._mocks["outreach_campaigns"].update.call_args[0][0]
        assert payload["status"] == "drafted"
        assert payload["send_error"] == "token_expired"

    def test_no_attach_resume_skips_app_lookup(self):
        db = self._run(_campaign(), attach_resume=False)
        assert "generated_applications" not in db._mocks

    def test_outlook_provider_calls_send_outlook(self):
        from app.services.email_sender import SendResult, email_sender

        result = SendResult(success=True, message_id="msg-1", thread_id="t-1")
        db = _make_db(campaign=_campaign(), profile=_profile(), app_data=_app())

        mock_gmail = AsyncMock(return_value=result)
        mock_outlook = AsyncMock(return_value=result)

        with (
            patch("app.tasks.outreach_tasks._db", return_value=db),
            patch.object(email_sender, "send_gmail", new=mock_gmail),
            patch.object(email_sender, "send_outlook", new=mock_outlook),
        ):
            from app.tasks.outreach_tasks import send_email_task
            send_email_task.run(_campaign()["id"], provider="outlook", attach_resume=False)

        mock_outlook.assert_called_once()
        mock_gmail.assert_not_called()


# ── discover_contact_task ─────────────────────────────────────────────────────

class TestDiscoverContactTask:

    def _run(self, campaign: dict, contact_result) -> MagicMock:
        from app.tasks.outreach_tasks import discover_contact_task
        from app.services.contact_finder import contact_finder

        db = _make_db(campaign=campaign, app_data=_app(), job=_job())

        with (
            patch("app.tasks.outreach_tasks._db", return_value=db),
            patch.object(contact_finder, "discover", new=AsyncMock(return_value=contact_result)),
        ):
            discover_contact_task.run(campaign["id"])

        return db

    def test_contact_found_writes_all_fields(self):
        from app.services.contact_finder import ContactResult

        contact = ContactResult(
            name="Jane Doe",
            title="Recruiter",
            email="jane@corp.com",
            verified=True,
            method="hunter",
            linkedin="linkedin.com/in/jane",
        )
        db = self._run(_campaign(), contact)

        payload = db._mocks["outreach_campaigns"].update.call_args[0][0]
        assert payload["contact_name"] == "Jane Doe"
        assert payload["contact_email"] == "jane@corp.com"
        assert payload["contact_title"] == "Recruiter"
        assert payload["email_verified"] is True
        assert payload["verification_method"] == "hunter"
        assert payload["contact_linkedin"] == "linkedin.com/in/jane"

    def test_contact_not_found_does_not_update(self):
        db = self._run(_campaign(), contact_result=None)
        db._mocks["outreach_campaigns"].update.assert_not_called()


# ── draft_email_task ──────────────────────────────────────────────────────────

class TestDraftEmailTask:

    def _run(self, campaign: dict, draft_result=None, raise_exc=None) -> MagicMock:
        from app.tasks.outreach_tasks import draft_email_task
        from app.services.email_drafter import email_drafter

        db = _make_db(campaign=campaign, app_data=_app(), job=_job(), profile=_profile())
        mock_draft = (
            AsyncMock(side_effect=raise_exc)
            if raise_exc
            else AsyncMock(return_value=draft_result)
        )

        try:
            with (
                patch("app.tasks.outreach_tasks._db", return_value=db),
                patch.object(email_drafter, "draft", new=mock_draft),
            ):
                draft_email_task.run(campaign["id"])
        except Exception:
            pass

        return db

    def test_successful_draft_writes_subject_body_context(self):
        class _Draft:
            subject = "Great opportunity at Acme"
            body = "Hi Alice, I came across..."
            company_context = {"funding_stage": "Series B"}

        db = self._run(_campaign(), draft_result=_Draft())

        payload = db._mocks["outreach_campaigns"].update.call_args[0][0]
        assert payload["email_subject"] == "Great opportunity at Acme"
        assert payload["email_body"] == "Hi Alice, I came across..."
        assert payload["company_context"] == {"funding_stage": "Series B"}

    def test_llm_exception_does_not_write_to_db(self):
        db = self._run(_campaign(), raise_exc=RuntimeError("LLM timeout"))
        db._mocks["outreach_campaigns"].update.assert_not_called()

    def test_draft_passes_contact_and_company_fields_to_drafter(self):
        """Verify the task forwards job/profile data into the drafter call."""
        from app.services.email_drafter import email_drafter

        class _Draft:
            subject = "Hi"
            body = "Body"
            company_context = {}

        mock_draft = AsyncMock(return_value=_Draft())
        db = _make_db(campaign=_campaign(), app_data=_app(), job=_job(), profile=_profile())

        with (
            patch("app.tasks.outreach_tasks._db", return_value=db),
            patch.object(email_drafter, "draft", new=mock_draft),
        ):
            from app.tasks.outreach_tasks import draft_email_task
            draft_email_task.run("camp-1")

        call_kwargs = mock_draft.call_args.kwargs
        assert call_kwargs["company_name"] == "Acme Corp"
        assert call_kwargs["role_title"] == "Software Engineer"
        assert call_kwargs["user_name"] == "John Smith"
        assert call_kwargs["contact_name"] == "Alice"
