import asyncio
import logging
from typing import AsyncIterable

from langgraph.runtime import Runtime
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

from naraninyeo.api.agents.information_gatherer import InformationGathererDeps, information_gatherer
from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)


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
