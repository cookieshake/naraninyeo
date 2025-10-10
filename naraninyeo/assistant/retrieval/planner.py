"""Retrieval planning driven by LLM prompts."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from opentelemetry.trace import get_tracer

from naraninyeo.assistant.llm_toolkit import LLMTool, LLMToolFactory
from naraninyeo.assistant.models import ReplyContext, RetrievalPlan
from naraninyeo.assistant.prompts import PlannerPrompt
from naraninyeo.settings import Settings


@dataclass
class RetrievalPlanLog:
    plan: RetrievalPlan
    matched: bool


class RetrievalPlanner:
    """Ask the LLM to decide which retrieval strategies to try."""

    def __init__(self, settings: Settings, llm_factory: LLMToolFactory):
        self.settings = settings
        self.tool: LLMTool[PlannerPrompt, list[RetrievalPlan]] = llm_factory.planner_tool()

    @get_tracer(__name__).start_as_current_span("plan retrieval")
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]:
        prompt = PlannerPrompt(context=context)
        # 대화 맥락을 모아 LLM에게 어떤 검색이 필요한지 계획부터 요청한다.
        plans = await self.tool.run(prompt)
        logging.debug("Retrieval plans generated: %s", [p.model_dump() for p in plans or []])
        return list(plans or [])
