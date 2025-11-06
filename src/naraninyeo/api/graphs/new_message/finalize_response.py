import logging

from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)


async def finalize_response(state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]) -> dict:
    logging.info("Finalizing response")
    state.outgoing_messages = []
    if len(state.draft_messages) == 0:
        return {}
    return {
        "outgoing_messages": state.outgoing_messages + state.draft_messages,
        "draft_messages": [],
    }
