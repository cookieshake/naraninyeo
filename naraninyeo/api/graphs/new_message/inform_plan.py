from langgraph.runtime import Runtime

from naraninyeo.api.agents.execution_informer import ExecutionInformerDeps, execution_informer
from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)
from naraninyeo.core.models import BotMessage, MessageContent


async def inform_plan(state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]) -> dict:
    state.outgoing_messages = []
    if state.response_plan is None:
        return {}
    if not state.response_plan.actions:
        return {}
    deps = ExecutionInformerDeps(
        plan=state.response_plan,
        incoming_message=state.incoming_message,
        history_messages=state.latest_history or [],
        is_retry=state.evaluation_count > 0,
    )
    informed_message = await execution_informer.run_with_generator(deps)
    return {
        "outgoing_messages": [
            BotMessage(
                content=MessageContent(
                    text=informed_message.output.message,
                ),
                bot=state.current_bot,
                channel=state.incoming_message.channel,
            )
        ]
    }
