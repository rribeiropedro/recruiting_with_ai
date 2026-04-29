"""Unit tests for EmailDrafter service (app/services/email_drafter.py)."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBuildPrompt:
    def _drafter(self):
        from app.services.email_drafter import EmailDrafter

        return EmailDrafter()

    def test_contains_company_name(self):
        result = self._drafter()._build_prompt(
            company_name="Acme Corp",
            company_context={},
            contact_name="Jane",
            contact_title="Recruiter",
            role_title="Software Engineer",
            resume_summary="5 years Python",
            user_name="John Smith",
            tone="conversational",
        )
        assert "COMPANY: Acme Corp" in result

    def test_none_company_name_uses_unknown(self):
        result = self._drafter()._build_prompt(
            company_name=None,
            company_context={},
            contact_name=None,
            contact_title=None,
            role_title="SWE",
            resume_summary="",
            user_name="John",
            tone="professional",
        )
        assert "COMPANY: Unknown" in result

    def test_none_contact_name_falls_back_to_hiring_manager(self):
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context={},
            contact_name=None,
            contact_title=None,
            role_title="SWE",
            resume_summary="",
            user_name="John",
            tone="conversational",
        )
        assert "HIRING MANAGER: Hiring Manager, unknown title" in result

    def test_named_contact_used_when_present(self):
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context={},
            contact_name="Alice",
            contact_title="CTO",
            role_title="SWE",
            resume_summary="",
            user_name="John",
            tone="bold",
        )
        assert "HIRING MANAGER: Alice, CTO" in result

    def test_tone_included(self):
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context={},
            contact_name=None,
            contact_title=None,
            role_title="SWE",
            resume_summary="",
            user_name="John",
            tone="bold",
        )
        assert "TONE: bold" in result

    def test_company_context_serialized_as_json(self):
        ctx = {"funding_stage": "Series B", "recent_news": ["IPO planned"]}
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context=ctx,
            contact_name=None,
            contact_title=None,
            role_title="SWE",
            resume_summary="",
            user_name="John",
            tone="conversational",
        )
        assert json.dumps(ctx) in result

    def test_resume_summary_included(self):
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context={},
            contact_name=None,
            contact_title=None,
            role_title="SWE",
            resume_summary="Led migration saving $2M annually",
            user_name="John",
            tone="conversational",
        )
        assert "Led migration saving $2M annually" in result

    def test_candidate_name_included(self):
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context={},
            contact_name=None,
            contact_title=None,
            role_title="SWE",
            resume_summary="",
            user_name="Maria Garcia",
            tone="conversational",
        )
        assert "CANDIDATE NAME: Maria Garcia" in result

    def test_role_title_included(self):
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context={},
            contact_name=None,
            contact_title=None,
            role_title="Machine Learning Engineer",
            resume_summary="",
            user_name="John",
            tone="conversational",
        )
        assert "ROLE: Machine Learning Engineer" in result

    def test_none_role_title_uses_open_position(self):
        result = self._drafter()._build_prompt(
            company_name="Corp",
            company_context={},
            contact_name=None,
            contact_title=None,
            role_title=None,
            resume_summary="",
            user_name="John",
            tone="conversational",
        )
        assert "ROLE: the open position" in result


class TestParseEmail:
    def _drafter(self):
        from app.services.email_drafter import EmailDrafter

        return EmailDrafter()

    def test_extracts_subject_from_labeled_line(self):
        raw = "Subject: Great Opportunity at Acme\n\nHi there,\n\nBody text.\n\nJohn"
        subject, body = self._drafter()._parse_email(raw, "SWE", "John Smith")
        assert subject == "Great Opportunity at Acme"

    def test_body_does_not_contain_subject_line(self):
        raw = "Subject: Test Subject\n\nActual body content here"
        subject, body = self._drafter()._parse_email(raw, "SWE", "John")
        assert "Subject:" not in body
        assert "Test Subject" not in body

    def test_body_content_preserved(self):
        raw = "Subject: Hi\n\nParagraph one.\n\nParagraph two.\n\nJohn"
        _, body = self._drafter()._parse_email(raw, "SWE", "John")
        assert "Paragraph one." in body
        assert "Paragraph two." in body
        assert "John" in body

    def test_subject_label_is_case_insensitive(self):
        raw = "SUBJECT: Upper Case Label\n\nBody"
        subject, _ = self._drafter()._parse_email(raw, "SWE", "John")
        assert subject == "Upper Case Label"

    def test_subject_value_is_stripped(self):
        raw = "Subject:   Leading and trailing spaces   \n\nBody"
        subject, _ = self._drafter()._parse_email(raw, "SWE", "John")
        assert subject == "Leading and trailing spaces"

    def test_fallback_subject_uses_role_and_name(self):
        """No Subject: line → fall back to '{role_title} — {user_name}'."""
        raw = "Hi there,\n\nNo subject line.\n\nJohn"
        subject, _ = self._drafter()._parse_email(raw, "Software Engineer", "John Smith")
        assert subject == "Software Engineer — John Smith"

    def test_fallback_subject_no_role_title_uses_open_position(self):
        raw = "Just a body, no subject."
        subject, _ = self._drafter()._parse_email(raw, None, "Jane Doe")
        assert subject == "Open Position — Jane Doe"

    def test_empty_response_returns_fallback_subject_and_empty_body(self):
        subject, body = self._drafter()._parse_email("", "Engineer", "Alex")
        assert subject == "Engineer — Alex"
        assert body == ""

    def test_body_stripped_of_leading_trailing_whitespace(self):
        raw = "Subject: Hi\n\n\n\n   Body starts here   \n\n"
        _, body = self._drafter()._parse_email(raw, "SWE", "John")
        assert body == "Body starts here"


class TestResearchCompany:
    async def test_empty_company_name_returns_empty_dict(self):
        from app.services.email_drafter import EmailDrafter

        drafter = EmailDrafter()
        result = await drafter._research_company(None, "fintech")
        assert result == {}

    async def test_returns_cached_result_on_hit(self):
        from app.services.email_drafter import EmailDrafter

        drafter = EmailDrafter()
        cached = {"company_name": "Acme", "industry": "saas", "recent_news": [], "company_description": ""}

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached))

        with patch("app.services.email_drafter._get_redis", return_value=mock_redis):
            result = await drafter._research_company("Acme", "saas")

        assert result == cached
        mock_redis.setex.assert_not_called()

    async def test_builds_context_dict_on_cache_miss(self):
        from app.services.email_drafter import EmailDrafter

        drafter = EmailDrafter()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch("app.services.email_drafter._get_redis", return_value=mock_redis):
            result = await drafter._research_company("Acme Corp", "fintech")

        assert result["company_name"] == "Acme Corp"
        assert result["industry"] == "fintech"
        assert "recent_news" in result
        assert "company_description" in result

    async def test_caches_result_for_24_hours(self):
        from app.services.email_drafter import EmailDrafter

        drafter = EmailDrafter()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with patch("app.services.email_drafter._get_redis", return_value=mock_redis):
            await drafter._research_company("Acme Corp", "fintech")

        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[1] == 86400

    async def test_cache_key_is_normalised(self):
        """'Acme Corp' and 'acme corp' should use the same cache key."""
        from app.services.email_drafter import EmailDrafter

        drafter = EmailDrafter()
        keys_used: list[str] = []

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        async def capture_setex(key, ttl, value):
            keys_used.append(key)

        mock_redis.setex = capture_setex

        with patch("app.services.email_drafter._get_redis", return_value=mock_redis):
            await drafter._research_company("Acme Corp", "saas")

        assert keys_used[0] == "company_ctx:acme_corp"
