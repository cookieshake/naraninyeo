import logging

from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)


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
