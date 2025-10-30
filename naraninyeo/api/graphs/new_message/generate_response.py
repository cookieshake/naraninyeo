import re

from langgraph.runtime import Runtime

from naraninyeo.api.agents.response_generator import ResponseGeneratorDeps, response_generator
from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)
from naraninyeo.core.models import BotMessage, MessageContent


async def generate_response(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    if (
        state.response_plan is None
        or state.incoming_message is None
    ):
        return state
    if state.draft_messages is None:
        state.draft_messages = []

    deps = ResponseGeneratorDeps(
        bot=state.current_bot,
        incoming_message=state.incoming_message,
        latest_messages=state.latest_history or [],
        plan=state.response_plan,
        plan_action_results=state.plan_action_results or [],
        clock=runtime.context.clock,
        memories=state.memories
    )

    generated_response = await response_generator.run_with_generator(deps)
    for part in re.split(r'\n\n+', generated_response.output):
        state.draft_messages.append(BotMessage(
            bot=state.current_bot,
            channel=state.incoming_message.channel,
            content=MessageContent(text=part)
        ))
    return state
