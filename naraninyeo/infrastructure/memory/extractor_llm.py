from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from textwrap import dedent
from typing import Literal

from pydantic import BaseModel, Field

from naraninyeo.core.contracts.memory import MemoryExtractor
from naraninyeo.core.llm.agent import Agent
from naraninyeo.core.llm.spec import list_of
from naraninyeo.core.models.memory import MemoryItem
from naraninyeo.core.models.message import Message
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory
from naraninyeo.infrastructure.settings import Settings


class LLMExtractionItem(BaseModel):
    content: str = Field(min_length=1, max_length=200)
    importance: int = Field(default=1, ge=1, le=5)
    kind: Literal["ephemeral", "persona", "task"] = "ephemeral"
    ttl_hours: int | None = Field(default=None, ge=1, le=48)


class LLMMemoryExtractor(MemoryExtractor):
    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory):
        self.settings = settings
        self.agent: Agent[list[LLMExtractionItem]] = llm_factory.memory_agent(output_type=list_of(LLMExtractionItem))

    async def extract_from_message(self, message: Message, history: list[Message]) -> list[MemoryItem]:
        # Skip commands
        if (message.content.text or "").strip().startswith("/"):
            return []

        his = "\n".join([m.text_repr for m in history[-10:]])
        prompt = dedent(
            f"""
            최근 대화 기록:
            ---
            {his}
            ---

            새 메시지:
            {message.text_repr}
            """
        ).strip()

        try:
            result = await self.agent.run(prompt)
            items: list[LLMExtractionItem] = result.output or []
        except Exception:
            return []

        now = datetime.now(timezone.utc)
        out: list[MemoryItem] = []
        for it in items[:3]:
            ttl = it.ttl_hours if it.ttl_hours is not None else self.settings.MEMORY_TTL_HOURS
            expires = now + timedelta(hours=int(ttl))
            out.append(
                MemoryItem(
                    memory_id=str(uuid.uuid4()),
                    channel_id=message.channel.channel_id,
                    kind=it.kind,
                    content=it.content.strip(),
                    importance=it.importance,
                    created_at=now,
                    expires_at=expires,
                )
            )
        return out
