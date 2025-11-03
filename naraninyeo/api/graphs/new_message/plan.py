from langgraph.runtime import Runtime

from naraninyeo.api.agents.response_planner import ResponsePlannerDeps, response_planner
from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)
from naraninyeo.core.models import ResponsePlan


async def plan(state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]) -> NewMessageGraphState:
    if state.incoming_message is None:
        return state

    if response_planner.model is None:
        state.response_plan = ResponsePlan(
            actions=[],
            generation_instructions="사용자 메시지에 짧고 친근하게 반말로 답해주세요.",
        )
        return state

    deps = ResponsePlannerDeps(
        bot=state.current_bot,
        incoming_message=state.incoming_message,
        latest_messages=state.latest_history or [],
        memories=state.memories,
    )

    plan = await response_planner.run_with_generator(deps)
    state.response_plan = plan.output
    return state
