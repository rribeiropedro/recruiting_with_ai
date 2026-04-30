"""Unit tests for ContactFinder service (app/services/contact_finder.py)."""
from unittest.mock import AsyncMock, MagicMock, patch


def _make_hunter_contacts(titles: list[str]) -> list[dict]:
    return [
        {
            "value": f"user{i}@corp.com",
            "position": title,
            "first_name": f"User{i}",
            "last_name": "Test",
            "linkedin": None,
        }
        for i, title in enumerate(titles)
    ]


class TestHunterTitleScoring:
    """Title priority: hiring manager > recruiter > talent acquisition > engineering manager ..."""

    async def _search(self, finder, titles):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"emails": _make_hunter_contacts(titles)}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        with patch.object(finder, "_verify_email", new=AsyncMock(return_value=True)):
            return await finder._hunter_search("example.com", "Engineer")

    async def test_hiring_manager_beats_recruiter(self):
        from app.services.contact_finder import ContactFinder

        result = await self._search(ContactFinder(), ["Recruiter", "Hiring Manager"])
        assert result is not None
        assert result.title == "Hiring Manager"

    async def test_recruiter_beats_engineering_manager(self):
        from app.services.contact_finder import ContactFinder

        result = await self._search(ContactFinder(), ["Engineering Manager", "Recruiter"])
        assert result is not None
        assert result.title == "Recruiter"

    async def test_talent_acquisition_match_via_substring(self):
        """'Talent Acquisition Lead' should match the 'talent acquisition' keyword."""
        from app.services.contact_finder import ContactFinder

        result = await self._search(ContactFinder(), ["Talent Acquisition Lead"])
        assert result is not None

    async def test_cto_scores_lower_than_hiring_manager(self):
        from app.services.contact_finder import ContactFinder

        result = await self._search(ContactFinder(), ["CTO", "Hiring Manager"])
        assert result is not None
        assert result.title == "Hiring Manager"

    async def test_no_priority_titles_returns_none(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {"emails": _make_hunter_contacts(["Software Engineer", "Designer"])}
        }
        finder._client.get = AsyncMock(return_value=mock_resp)
        result = await finder._hunter_search("example.com", "Engineer")
        assert result is None

    async def test_empty_contacts_returns_none(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"emails": []}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        result = await finder._hunter_search("example.com", "Engineer")
        assert result is None

    async def test_contact_name_assembled_from_first_last(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        contacts = [
            {
                "value": "jane@corp.com",
                "position": "Recruiter",
                "first_name": "Jane",
                "last_name": "Doe",
                "linkedin": "linkedin.com/in/jane",
            }
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"emails": contacts}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        with patch.object(finder, "_verify_email", new=AsyncMock(return_value=True)):
            result = await finder._hunter_search("example.com", "Engineer")

        assert result.name == "Jane Doe"
        assert result.email == "jane@corp.com"
        assert result.method == "hunter"
        assert result.verified is True

    async def test_missing_name_parts_yield_none_not_spaces(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        contacts = [
            {"value": "anon@corp.com", "position": "Recruiter", "first_name": "", "last_name": ""}
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"emails": contacts}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        with patch.object(finder, "_verify_email", new=AsyncMock(return_value=True)):
            result = await finder._hunter_search("example.com", "Engineer")

        assert result.name is None

    async def test_http_error_returns_none(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        finder._client.get = AsyncMock(side_effect=Exception("connection refused"))
        result = await finder._hunter_search("example.com", "Engineer")
        assert result is None

    async def test_no_api_key_returns_none(self, monkeypatch):
        from app.config import settings
        from app.services.contact_finder import ContactFinder

        monkeypatch.setattr(settings, "HUNTER_API_KEY", "")
        finder = ContactFinder()
        result = await finder._hunter_search("example.com", "Engineer")
        assert result is None


class TestVerifyEmail:
    async def test_deliverable_returns_true(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"result": "deliverable"}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        assert await finder._verify_email("test@example.com") is True

    async def test_risky_returns_true(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"result": "risky"}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        assert await finder._verify_email("test@example.com") is True

    async def test_undeliverable_returns_false(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"result": "undeliverable"}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        assert await finder._verify_email("test@example.com") is False

    async def test_unknown_result_returns_false(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"result": "unknown"}}
        finder._client.get = AsyncMock(return_value=mock_resp)
        assert await finder._verify_email("test@example.com") is False

    async def test_http_error_returns_false(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        finder._client.get = AsyncMock(side_effect=Exception("timeout"))
        assert await finder._verify_email("test@example.com") is False

    async def test_no_api_key_returns_false(self, monkeypatch):
        from app.config import settings
        from app.services.contact_finder import ContactFinder

        monkeypatch.setattr(settings, "HUNTER_API_KEY", "")
        finder = ContactFinder()
        assert await finder._verify_email("test@example.com") is False


class TestApolloSearch:
    async def test_returns_first_person(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        people = [
            {
                "name": "Alice Smith",
                "title": "Engineering Manager",
                "email": "alice@corp.com",
                "linkedin_url": "linkedin.com/in/alice",
            },
            {
                "name": "Bob Jones",
                "title": "VP Engineering",
                "email": "bob@corp.com",
                "linkedin_url": None,
            },
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"people": people}
        finder._client.post = AsyncMock(return_value=mock_resp)

        result = await finder._apollo_search("Corp Inc", "Engineer")

        assert result is not None
        assert result.name == "Alice Smith"
        assert result.email == "alice@corp.com"
        assert result.method == "apollo"
        assert result.verified is True

    async def test_empty_people_list_returns_none(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"people": []}
        finder._client.post = AsyncMock(return_value=mock_resp)

        assert await finder._apollo_search("Corp", "Engineer") is None

    async def test_person_without_email_sets_verified_false(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        people = [{"name": "Ghost", "title": "Recruiter", "email": None, "linkedin_url": None}]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"people": people}
        finder._client.post = AsyncMock(return_value=mock_resp)

        result = await finder._apollo_search("Corp", "Engineer")
        assert result.verified is False

    async def test_http_error_returns_none(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        finder._client.post = AsyncMock(side_effect=Exception("connection error"))
        assert await finder._apollo_search("Corp", "Engineer") is None

    async def test_no_api_key_returns_none(self, monkeypatch):
        from app.config import settings
        from app.services.contact_finder import ContactFinder

        monkeypatch.setattr(settings, "APOLLO_API_KEY", "")
        finder = ContactFinder()
        assert await finder._apollo_search("Corp", "Engineer") is None


class TestDiscover:
    async def test_returns_hunter_result_when_domain_found(self):
        from app.services.contact_finder import ContactFinder, ContactResult

        finder = ContactFinder()
        expected = ContactResult(
            name="Jane Doe", title="Recruiter", email="jane@corp.com",
            verified=True, method="hunter"
        )
        with (
            patch.object(finder, "_find_domain", new=AsyncMock(return_value="corp.com")),
            patch.object(finder, "_hunter_search", new=AsyncMock(return_value=expected)),
        ):
            result = await finder.discover("Corp Inc", "Engineer")

        assert result is expected

    async def test_falls_back_to_apollo_when_hunter_returns_none(self):
        from app.services.contact_finder import ContactFinder, ContactResult

        finder = ContactFinder()
        apollo_result = ContactResult(
            name="Bob", title="VP Engineering", email="bob@corp.com",
            verified=True, method="apollo"
        )
        with (
            patch.object(finder, "_find_domain", new=AsyncMock(return_value="corp.com")),
            patch.object(finder, "_hunter_search", new=AsyncMock(return_value=None)),
            patch.object(finder, "_apollo_search", new=AsyncMock(return_value=apollo_result)),
        ):
            result = await finder.discover("Corp Inc", "Engineer")

        assert result is apollo_result

    async def test_falls_back_to_apollo_when_no_domain(self):
        from app.services.contact_finder import ContactFinder, ContactResult

        finder = ContactFinder()
        apollo_result = ContactResult(
            name="Carol", title="Recruiter", email="carol@corp.com",
            verified=True, method="apollo"
        )
        with (
            patch.object(finder, "_find_domain", new=AsyncMock(return_value=None)),
            patch.object(finder, "_apollo_search", new=AsyncMock(return_value=apollo_result)),
        ):
            result = await finder.discover("Corp Inc", "Engineer")

        assert result is apollo_result

    async def test_returns_none_when_both_fail(self):
        from app.services.contact_finder import ContactFinder

        finder = ContactFinder()
        with (
            patch.object(finder, "_find_domain", new=AsyncMock(return_value=None)),
            patch.object(finder, "_apollo_search", new=AsyncMock(return_value=None)),
        ):
            result = await finder.discover("Unknown Corp", "Engineer")

        assert result is None
