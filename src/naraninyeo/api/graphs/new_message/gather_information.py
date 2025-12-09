from langgraph.runtime import Runtime

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
    )

    gatherer_result = await information_gatherer.run_with_generator(
        deps=deps,
    )

    state.information_gathering_results = gatherer_result.output
    return state
