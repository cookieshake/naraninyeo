
from typing import List, Literal, Optional

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from naraninyeo.api.graphs.new_message.evaluate_response import evaluate_response
from naraninyeo.api.graphs.new_message.execute_plan import execute_plan
from naraninyeo.api.graphs.new_message.finalize_response import finalize_response
from naraninyeo.api.graphs.new_message.generate_response import generate_response
from naraninyeo.api.graphs.new_message.plan import plan
from naraninyeo.api.infrastructure.interfaces import Clock, MemoryRepository, MessageRepository, PlanActionExecutor
from naraninyeo.core.models import (
    Bot,
    BotMessage,
    EvaluationFeedback,
    MemoryItem,
    Message,
    PlanActionResult,
    ResponsePlan,
    TenancyContext,
)


class NewMessageGraphState(BaseModel):
    current_tctx: TenancyContext
    current_bot: Bot
    memories: List[MemoryItem]
    status: Literal["processing", "completed", "failed"]
    incoming_message: Message
    latest_history: Optional[List[Message]] = None
    response_plan: Optional[ResponsePlan] = None
    plan_action_results: Optional[List[PlanActionResult]] = None
    latest_evaluation_feedback: Optional[EvaluationFeedback] = None
    draft_messages: Optional[List[BotMessage]] = None
    outgoing_messages: Optional[List[BotMessage]] = None

class NewMessageGraphContext(BaseModel):
    clock: Clock
    message_repository: MessageRepository
    memory_repository: MemoryRepository
    plan_action_executor: PlanActionExecutor

_new_message_graph = StateGraph(
    state_schema=NewMessageGraphState, context_schema=NewMessageGraphContext
)

_new_message_graph.add_node("plan", plan)
_new_message_graph.add_node("execute_plan", execute_plan)
_new_message_graph.add_node("generate_response", generate_response)
_new_message_graph.add_node("evaluate_response", evaluate_response)
_new_message_graph.add_node("finalize_response", finalize_response)

_new_message_graph.add_edge(START, "plan")

def response_or_not(state: NewMessageGraphState) -> str:
    if state.incoming_message and state.incoming_message.content.text.strip():
        return "plan"
    else:
        return END

_new_message_graph.add_conditional_edges("save_message", response_or_not)
_new_message_graph.add_edge("plan", "execute_plans")
_new_message_graph.add_edge("execute_plans", "generate_response")
_new_message_graph.add_edge("generate_response", "evaluate_response")

def route_based_on_evaluation(state: NewMessageGraphState) -> str:
    if state.latest_evaluation_feedback == EvaluationFeedback.PLAN_AGAIN:
        return "plan"
    elif state.latest_evaluation_feedback == EvaluationFeedback.EXECUTE_AGAIN:
        return "execute_plans"
    elif state.latest_evaluation_feedback == EvaluationFeedback.GENERATE_AGAIN:
        return "generate_response"
    elif state.latest_evaluation_feedback == EvaluationFeedback.FINALIZE:
        return END
    else:
        return START

_new_message_graph.add_conditional_edges("evaluate_response", route_based_on_evaluation)

new_message_graph = _new_message_graph.compile()
