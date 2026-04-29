from typing import Literal
from uuid import UUID

import anthropic
import openai
import structlog

from ..config import settings

logger = structlog.get_logger()

PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-haiku-4-5-20251001": {"input": 0.25 / 1_000_000, "output": 1.25 / 1_000_000},
    "text-embedding-3-small": {"input": 0.02 / 1_000_000, "output": 0.0},
}


class LLMClient:
    def __init__(self):
        self._anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._openai = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        response_format: Literal["text", "json"] = "text",
        user_id: UUID | None = None,
        task_type: str | None = None,
        prompt_version: str | None = None,
    ) -> str:
        message = await self._anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        cost = (
            input_tokens * PRICING[model]["input"]
            + output_tokens * PRICING[model]["output"]
        )
        logger.info(
            "llm_call",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            task_type=task_type,
            prompt_version=prompt_version,
            user_id=str(user_id) if user_id else None,
        )
        return message.content[0].text

    async def embed(self, text: str, user_id: UUID | None = None) -> list[float]:
        response = await self._openai.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding


llm_client = LLMClient()
