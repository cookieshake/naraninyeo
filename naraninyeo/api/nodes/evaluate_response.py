from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState
from naraninyeo.core.models import BotMessage, MessageContent


async def evaluate_response(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    if state.draft_messages is None:
        return state
    state.latest_evaluation_feedback = "finalize"

    return state
