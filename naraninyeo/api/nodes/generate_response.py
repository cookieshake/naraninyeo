from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState
from naraninyeo.core.models import BotMessage, MessageContent


async def generate_response(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    if state.draft_messages is None:
        state.draft_messages = []
    state.draft_messages.append(BotMessage(
        bot=state.current_bot,
        channel=state.incoming_message.channel,
        content=MessageContent(text="This is a generated response.")
    ))
    return state
