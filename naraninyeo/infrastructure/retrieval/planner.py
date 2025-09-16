import logging
from textwrap import dedent

from opentelemetry.trace import get_tracer

from naraninyeo.core.llm.agent import Agent
from naraninyeo.core.llm.spec import list_of
from naraninyeo.core.models.reply import ReplyContext
from naraninyeo.core.models.retrieval import RetrievalPlan
from naraninyeo.infrastructure.llm.factory import LLMAgentFactory
from naraninyeo.infrastructure.settings import Settings


class RetrievalPlannerAgent:
    @get_tracer(__name__).start_as_current_span("plan retrieval")
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]:
        mem_text = (
            "\n".join([m.content for m in (context.short_term_memory or [])])
            if getattr(context, "short_term_memory", None)
            else "(없음)"
        )

        message = dedent(
            f"""
        직전 대화 기록:
        ---
        {"\n".join([msg.text_repr for msg in context.latest_history])}
        ---

        새로 들어온 메시지:
        {context.last_message.text_repr}

        단기 기억(있다면 우선 고려):
        ---
        {mem_text}
        ---

        위 메시지에 답하기 위해 어떤 종류의 검색을 어떤 검색어로 해야할까요?
        참고할만한 예전 대화 기록을 활용하여 더 정확한 검색 계획을 수립하세요.
        """
        ).strip()

        result = await self.agent.run(message)
        plans = result.output

        logging.debug(f"Retrieval plans generated: {[p.model_dump() for p in plans]}")
        return list(plans)

    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory):
        self.settings = settings
        # Keep original system prompt semantics via factory
        self.agent: Agent[list[RetrievalPlan]] = llm_factory.planner_agent(output_type=list_of(RetrievalPlan))
