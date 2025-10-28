from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState
from naraninyeo.core.models import ResponsePlan


async def plan(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    new_plan = ResponsePlan(
        actions=[],
        generation_instructions="Generate a response based on the message."
    )
    state.response_plan = new_plan

    return state
