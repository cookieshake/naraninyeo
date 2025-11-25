from langgraph.graph import START, StateGraph

from naraninyeo.api.graphs.new_message.evaluate_response import evaluate_response
from naraninyeo.api.graphs.new_message.finalize_response import finalize_response
from naraninyeo.api.graphs.new_message.gather_information import gather_information
from naraninyeo.api.graphs.new_message.generate_response import generate_response
from naraninyeo.api.graphs.new_message.models import (
    NewMessageGraphContext,
    NewMessageGraphState,
)
from naraninyeo.core.models import EvaluationFeedback

_new_message_graph = StateGraph(
    state_schema=NewMessageGraphState,
    context_schema=NewMessageGraphContext,
)

_new_message_graph.add_node("gather_information", gather_information)
_new_message_graph.add_node("generate_response", generate_response)
_new_message_graph.add_node("evaluate_response", evaluate_response)
_new_message_graph.add_node("finalize_response", finalize_response)

_new_message_graph.add_edge(START, "gather_information")
_new_message_graph.add_edge("gather_information", "generate_response")
_new_message_graph.add_edge("generate_response", "evaluate_response")


def route_based_on_evaluation(state: NewMessageGraphState) -> str:
    if state.latest_evaluation_feedback == EvaluationFeedback.PLAN_AGAIN:
        return "gather_information"
    elif state.latest_evaluation_feedback == EvaluationFeedback.EXECUTE_AGAIN:
        return "gather_information"
    elif state.latest_evaluation_feedback == EvaluationFeedback.GENERATE_AGAIN:
        return "generate_response"
    elif state.latest_evaluation_feedback == EvaluationFeedback.FINALIZE:
        return "finalize_response"
    else:
        raise ValueError(f"Unknown evaluation feedback: {state.latest_evaluation_feedback}")


_new_message_graph.add_conditional_edges("evaluate_response", route_based_on_evaluation)

new_message_graph = _new_message_graph.compile()
