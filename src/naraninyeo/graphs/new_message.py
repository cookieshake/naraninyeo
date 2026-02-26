"""New message processing graph.

Pipeline: check_profanity → gather_information → generate_response → evaluate_response → finalize_response
The evaluator may loop back to gather or generate if the response isn't good enough.
"""

import asyncio
import logging
import re
from typing import AsyncIterable, List, Literal, Optional

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelResponse,
    RunContext,
    UsageLimits,
    capture_run_messages,
)
from pydantic_ai.exceptions import UsageLimitExceeded

from naraninyeo.agents.information_gatherer import (
    InformationGathererDeps,
    InformationGathererOutput,
    information_gatherer,
)
from naraninyeo.agents.profanity_checker import ProfanityCheckerDeps, profanity_checker
from naraninyeo.agents.response_evaluator import ResponseEvaluatorDeps, response_evaluator
from naraninyeo.agents.response_generator import ResponseGeneratorDeps, response_generator
from naraninyeo.core.interfaces import (
    Clock,
    FinanceSearch,
    MemoryRepository,
    MessageRepository,
    NaverSearch,
    WebDocumentFetch,
)
from naraninyeo.core.models import (
    Bot,
    BotMessage,
    EvaluationFeedback,
    MemoryItem,
    Message,
    MessageContent,
    TenancyContext,
)

# ---------------------------------------------------------------------------
# State & Context
# ---------------------------------------------------------------------------


class NewMessageGraphState(BaseModel):
    current_tctx: TenancyContext
    current_bot: Bot
    memories: List[MemoryItem]
    status: Literal["processing", "completed", "failed"]
    incoming_message: Message
    latest_history: List[Message]
    evaluation_count: int = 0
    information_gathering_results: List[InformationGathererOutput] = Field(default_factory=list)
    latest_evaluation_feedback: Optional[EvaluationFeedback] = None
    is_profane: bool = False
    profanity_reason: Optional[str] = None
    draft_messages: List[BotMessage] = Field(default_factory=list)


class NewMessageGraphContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    clock: Clock
    message_repository: MessageRepository
    memory_repository: MemoryRepository
    naver_search_client: NaverSearch
    finance_search_client: FinanceSearch
    web_document_fetcher: WebDocumentFetch


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def check_profanity(
    state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    logging.info("Checking profanity")

    deps = ProfanityCheckerDeps(
        incoming_message=state.incoming_message,
    )

    result = await profanity_checker.run_with_generator(deps)
    state.is_profane = result.output.is_profane
    state.profanity_reason = result.output.reason

    if state.is_profane:
        logging.info(f"Profanity detected: {state.profanity_reason}")
        state.status = "completed"

    return state


async def gather_information(
    state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    deps = InformationGathererDeps(
        tctx=state.current_tctx,
        bot=state.current_bot,
        incoming_message=state.incoming_message,
        latest_messages=state.latest_history or [],
        memories=state.memories,
        message_repository=runtime.context.message_repository,
        naver_search_client=runtime.context.naver_search_client,
        finance_search_client=runtime.context.finance_search_client,
        web_document_fetcher=runtime.context.web_document_fetcher,
        use_tool_calls=True,
    )

    async def event_stream_handler(
        ctx: RunContext,
        event_stream: AsyncIterable[AgentStreamEvent],
    ):
        async for event in event_stream:
            match event:
                case FunctionToolCallEvent():
                    pass
                case FunctionToolResultEvent():
                    pass

    with capture_run_messages() as messages:
        try:
            async with asyncio.timeout(20.0):
                async with await information_gatherer.run_stream_with_generator(
                    deps=deps,
                    event_stream_handler=event_stream_handler,
                    usage_limits=UsageLimits(tool_calls_limit=20),
                ) as result:
                    state.information_gathering_results = await result.get_output()
        except (UsageLimitExceeded, TimeoutError) as e:
            match e:
                case UsageLimitExceeded():
                    logging.warning("Information gathering resource limit exceeded")
                case TimeoutError():
                    logging.warning("Information gathering timeout")
            # tool call이 마지막 메시지라면 제거
            latest = messages[-1]
            if isinstance(latest, ModelResponse) and latest.tool_calls:
                messages = messages[:-1]
            output = await information_gatherer.run(
                "주어진 자원을 사용하여 정보 수집을 완료하지 못했습니다. "
                "지금까지의 정보를 사용해서 빠르게 답변해주세요.",
                deps=deps.model_copy(update={"use_tool_calls": False}),
                message_history=messages,
            )
            state.information_gathering_results = output.output
    return state


async def generate_response(
    state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    if state.draft_messages is None:
        state.draft_messages = []

    deps = ResponseGeneratorDeps(
        bot=state.current_bot,
        incoming_message=state.incoming_message,
        latest_messages=state.latest_history or [],
        information_gathering_results=state.information_gathering_results or [],
        clock=runtime.context.clock,
        memories=state.memories,
    )

    generated_response = await response_generator.run_with_generator(deps)
    for part in re.split(r"\n\n+", generated_response.output):
        state.draft_messages.append(
            BotMessage(bot=state.current_bot, channel=state.incoming_message.channel, content=MessageContent(text=part))
        )
    return state


async def evaluate_response(
    state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    logging.info("Evaluating response")
    if state.evaluation_count > 1:
        state.latest_evaluation_feedback = EvaluationFeedback.FINALIZE
        return state

    evaluator_deps = ResponseEvaluatorDeps(
        bot=state.current_bot,
        incoming_message=state.incoming_message,
        latest_messages=state.latest_history,
        generated_responses=[msg.content.text for msg in state.draft_messages],
    )

    evaluation_feedback = await response_evaluator.run_with_generator(evaluator_deps)

    state.latest_evaluation_feedback = evaluation_feedback.output
    state.evaluation_count += 1
    if state.latest_evaluation_feedback != EvaluationFeedback.FINALIZE:
        state.draft_messages = []

    return state


async def finalize_response(
    state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    logging.info("Finalizing response")
    writer = get_stream_writer()
    for msg in state.draft_messages:
        writer(
            {
                "type": "response",
                "text": msg.content.text,
            }
        )
    return state


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def route_after_profanity_check(state: NewMessageGraphState) -> str:
    if state.is_profane:
        return END
    return "gather_information"


def route_based_on_evaluation(state: NewMessageGraphState) -> str:
    if state.latest_evaluation_feedback == EvaluationFeedback.PLAN_AGAIN:
        return "gather_information"
    elif state.latest_evaluation_feedback == EvaluationFeedback.EXECUTE_AGAIN:
        return "gather_information"
    elif state.latest_evaluation_feedback == EvaluationFeedback.GENERATE_AGAIN:
        return "generate_response"
    elif state.latest_evaluation_feedback == EvaluationFeedback.FINALIZE:
        return "finalize_response"
    else:
        raise ValueError(f"Unknown evaluation feedback: {state.latest_evaluation_feedback}")


_graph = StateGraph(
    state_schema=NewMessageGraphState,
    context_schema=NewMessageGraphContext,
)

_graph.add_node("check_profanity", check_profanity)
_graph.add_node("gather_information", gather_information)
_graph.add_node("generate_response", generate_response)
_graph.add_node("evaluate_response", evaluate_response)
_graph.add_node("finalize_response", finalize_response)

_graph.add_edge(START, "check_profanity")
_graph.add_conditional_edges("check_profanity", route_after_profanity_check)
_graph.add_edge("gather_information", "generate_response")
_graph.add_edge("generate_response", "evaluate_response")
_graph.add_conditional_edges("evaluate_response", route_based_on_evaluation)

new_message_graph = _graph.compile()
