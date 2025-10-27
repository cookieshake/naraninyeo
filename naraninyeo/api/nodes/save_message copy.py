from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState


async def save_message(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    repo = runtime.context.message_repository
    if state.incomming_message is not None:
        await repo.save(state.incomming_message)
    return state
