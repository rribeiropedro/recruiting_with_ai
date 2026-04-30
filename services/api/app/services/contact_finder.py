from dataclasses import dataclass

import httpx
import structlog

from ..config import settings

logger = structlog.get_logger()


@dataclass
class ContactResult:
    name: str | None
    title: str | None
    email: str | None
    verified: bool
    method: str
    linkedin: str | None = None


class ContactFinder:
    def __init__(self):
        self._client = httpx.AsyncClient(timeout=15.0)

    async def discover(self, company_name: str, role_title: str) -> ContactResult | None:
        domain = await self._find_domain(company_name)
        if domain:
            contact = await self._hunter_search(domain, role_title)
            if contact:
                return contact

        contact = await self._apollo_search(company_name, role_title)
        return contact

    async def _find_domain(self, company_name: str) -> str | None:
        if not settings.HUNTER_API_KEY:
            return None
        try:
            resp = await self._client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"company": company_name, "api_key": settings.HUNTER_API_KEY},
            )
            return resp.json().get("data", {}).get("domain")
        except Exception as e:
            logger.warning("hunter_domain_search_failed", error=str(e))
            return None

    async def _hunter_search(self, domain: str, role_title: str) -> ContactResult | None:
        if not settings.HUNTER_API_KEY:
            return None
        try:
            resp = await self._client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": settings.HUNTER_API_KEY, "limit": 10},
            )
            contacts = resp.json().get("data", {}).get("emails", [])
        except Exception as e:
            logger.warning("hunter_search_failed", error=str(e))
            return None

        title_keywords = [
            "hiring manager", "recruiter", "talent acquisition",
            "engineering manager", "head of engineering",
            "vp engineering", "director of engineering",
            "cto", "head of talent",
        ]

        best = None
        best_score = -1
        for c in contacts:
            title = (c.get("position") or "").lower()
            for i, kw in enumerate(title_keywords):
                if kw in title:
                    score = len(title_keywords) - i
                    if score > best_score:
                        best = c
                        best_score = score
                    break

        if not best:
            return None

        verified = await self._verify_email(best["value"])
        return ContactResult(
            name=f"{best.get('first_name', '')} {best.get('last_name', '')}".strip() or None,
            title=best.get("position"),
            email=best["value"],
            verified=verified,
            method="hunter",
            linkedin=best.get("linkedin"),
        )

    async def _verify_email(self, email: str) -> bool:
        if not settings.HUNTER_API_KEY:
            return False
        try:
            resp = await self._client.get(
                "https://api.hunter.io/v2/email-verifier",
                params={"email": email, "api_key": settings.HUNTER_API_KEY},
            )
            result = resp.json().get("data", {}).get("result")
            return result in ("deliverable", "risky")
        except Exception:
            return False

    async def _apollo_search(self, company_name: str, role_title: str) -> ContactResult | None:
        if not settings.APOLLO_API_KEY:
            return None
        try:
            resp = await self._client.post(
                "https://api.apollo.io/v1/mixed_people/search",
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": settings.APOLLO_API_KEY,
                },
                json={
                    "q_organization_name": company_name,
                    "person_titles": [
                        "Engineering Manager", "Hiring Manager", "Recruiter",
                        "Head of Engineering", "VP Engineering",
                    ],
                    "page": 1,
                    "per_page": 5,
                },
            )
            people = resp.json().get("people", [])
        except Exception as e:
            logger.warning("apollo_search_failed", error=str(e))
            return None

        if not people:
            return None

        person = people[0]
        return ContactResult(
            name=person.get("name"),
            title=person.get("title"),
            email=person.get("email"),
            verified=person.get("email") is not None,
            method="apollo",
            linkedin=person.get("linkedin_url"),
        )


contact_finder = ContactFinder()
