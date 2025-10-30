from langgraph.runtime import Runtime

from naraninyeo.api.agents.response_evaluator import ResponseEvaluatorDeps, response_evaluator
from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)

async def evaluate_response(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    if (
        state.draft_messages is None
        or state.response_plan is None
        or state.latest_history is None
    ):
        return state

    evaluator_deps = ResponseEvaluatorDeps(
        bot=state.current_bot,
        plan=state.response_plan,
        incoming_message=state.incoming_message,
        latest_messages=state.latest_history,
        generated_responses=[msg.content.text for msg in state.draft_messages]
    )

    evaluation_feedback = await response_evaluator.run_with_generator(
        evaluator_deps
    )

    state.latest_evaluation_feedback = evaluation_feedback.output
    return state
