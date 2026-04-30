import json
from dataclasses import dataclass
from typing import Any

import structlog

from ..config import settings
from ..prompts.draft_email import SYSTEM_PROMPT as DRAFT_EMAIL_SYSTEM_PROMPT
from ..prompts.draft_email import VERSION as DRAFT_EMAIL_VERSION
from ..services.llm_client import llm_client

logger = structlog.get_logger()

# Lazy redis import — avoids import errors when redis isn't running locally
_redis = None


def _get_redis() -> Any:
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            settings.REDIS_URL, decode_responses=True
        )
    return _redis


@dataclass
class EmailDraft:
    subject: str
    body: str
    company_context: dict[str, Any]


class EmailDrafter:
    async def draft(
        self,
        campaign_id: Any,
        application_id: Any,
        contact_name: str | None,
        contact_title: str | None,
        company_name: str | None,
        role_title: str | None,
        industry: str | None,
        resume_summary: str,
        user_name: str,
        user_id: Any,
        tone: str = "conversational",
    ) -> EmailDraft:
        company_context = await self._research_company(company_name, industry)

        user_prompt = self._build_prompt(
            company_name=company_name,
            company_context=company_context,
            contact_name=contact_name,
            contact_title=contact_title,
            role_title=role_title,
            resume_summary=resume_summary,
            user_name=user_name,
            tone=tone,
        )

        response = await llm_client.complete(
            system_prompt=DRAFT_EMAIL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model="claude-sonnet-4-20250514",
            user_id=user_id,
            task_type="draft_email",
            prompt_version=DRAFT_EMAIL_VERSION,
        )

        subject, body = self._parse_email(response, role_title, user_name)
        return EmailDraft(subject=subject, body=body, company_context=company_context)

    async def _research_company(
        self, company_name: str | None, industry: str | None
    ) -> dict[str, Any]:
        if not company_name:
            return {}

        cache_key = f"company_ctx:{company_name.lower().replace(' ', '_')}"
        try:
            r = _get_redis()  # type: ignore[no-untyped-call]
            cached = await r.get(cache_key)
            if cached:
                result: dict[str, Any] = json.loads(cached)
                return result
        except Exception:
            pass

        context: dict[str, Any] = {
            "company_name": company_name,
            "industry": industry,
            "recent_news": [],
            "company_description": "",
        }

        try:
            await r.setex(cache_key, 86400, json.dumps(context))
        except Exception:
            pass

        return context

    def _build_prompt(self, **kwargs: Any) -> str:
        parts = [
            f"COMPANY: {kwargs['company_name'] or 'Unknown'}",
            f"COMPANY CONTEXT: {json.dumps(kwargs['company_context'])}",
            (
                f"HIRING MANAGER: {kwargs['contact_name'] or 'Hiring Manager'},"
                f" {kwargs['contact_title'] or 'unknown title'}"
            ),
            f"ROLE: {kwargs['role_title'] or 'the open position'}",
            f"CANDIDATE NAME: {kwargs['user_name']}",
            f"CANDIDATE RESUME SUMMARY:\n{kwargs['resume_summary']}",
            f"TONE: {kwargs['tone']}",
        ]
        return "\n\n".join(parts)

    def _parse_email(
        self, raw_response: str, role_title: str | None, user_name: str
    ) -> tuple[str, str]:
        lines = raw_response.strip().split("\n")
        subject = None
        body_start = 0

        for i, line in enumerate(lines):
            if line.lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                body_start = i + 1
                break

        if not subject:
            subject = f"{role_title or 'Open Position'} — {user_name}"

        body = "\n".join(lines[body_start:]).strip()
        return subject, body


email_drafter = EmailDrafter()
