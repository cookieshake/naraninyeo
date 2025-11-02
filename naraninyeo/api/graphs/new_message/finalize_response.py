from langgraph.runtime import Runtime
from loguru import logger

from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)


async def finalize_response(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    logger.info("Finalizing response with state: {}", state.model_dump_json())
    if state.draft_messages is None:
        return state
    if state.outgoing_messages is None:
        state.outgoing_messages = []
    state.outgoing_messages.extend(state.draft_messages)
    state.draft_messages = []
    logger.info("Finalized response with state: {}", state.model_dump_json())
    return state
