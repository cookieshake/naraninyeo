from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)


async def execute_plan(state: NewMessageGraphState, runtime: Runtime[NewMessageGraphContext]) -> NewMessageGraphState:
    state.outgoing_messages = []
    executor = runtime.context.plan_action_executor
    if state.response_plan is None:
        return state
    execution_results = await executor.execute_actions(
        tctx=state.current_tctx,
        incoming_message=state.incoming_message,
        latest_history=state.latest_history,
        memories=state.memories,
        actions=state.response_plan.actions,
    )
    state.plan_action_results = execution_results
    return state
