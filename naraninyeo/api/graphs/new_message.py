
from typing import List, Literal, Optional, TypedDict

from langgraph.runtime import Runtime
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel


from naraninyeo.api.infrastructure.interfaces import Clock, MemoryRepository, MessageRepository, PlanActionExecutor
from naraninyeo.api.nodes.add_memory import add_memory
from naraninyeo.api.nodes.evaluate_response import evaluate_response
from naraninyeo.api.nodes.finalize_response import finalize_response
from naraninyeo.api.nodes.generate_response import generate_response
from naraninyeo.api.nodes.manage_memory import manage_memory
from naraninyeo.api.nodes.plan import plan
from naraninyeo.api.nodes.save_message import save_message
from naraninyeo.api.nodes.execute_plan import execute_plan
from naraninyeo.core.models import Bot, BotMessage, Message, PlanActionResult, ResponsePlan


class NewMessageGraphState(BaseModel):
    current_bot: Bot
    status: Literal["processing", "completed", "failed"]
    incoming_message: Message
    latest_history: Optional[List[Message]] = None
    response_plan: Optional[ResponsePlan] = None
    plan_action_results: Optional[List[PlanActionResult]] = None
    latest_evaluation_feedback: Optional[
        Literal["plan_again", "execute_again", "generate_again", "finalize"]
    ] = None
    draft_messages: Optional[List[BotMessage]] = None
    outgoing_messages: Optional[List[BotMessage]] = None

class NewMessageGraphContext(BaseModel):
    clock: Clock
    message_repository: MessageRepository
    memory_repository: MemoryRepository
    plan_action_executor: PlanActionExecutor

new_message_graph = StateGraph(
    state_schema=NewMessageGraphState, context_schema=NewMessageGraphContext
)

new_message_graph.add_node("save_message", save_message)
new_message_graph.add_node("add_memory", add_memory)
new_message_graph.add_node("manage_memory", manage_memory)
new_message_graph.add_node("plan", plan)
new_message_graph.add_node("execute_plan", execute_plan)
new_message_graph.add_node("generate_response", generate_response)
new_message_graph.add_node("evaluate_response", evaluate_response)
new_message_graph.add_node("finalize_response", finalize_response)

new_message_graph.set_entry_point("save_message")
new_message_graph.add_edge("save_message", "add_memory")

def response_or_not(state: NewMessageGraphState) -> str:
    if state.incoming_message and state.incoming_message.content.text.strip():
        return "plan"
    else:
        return END

new_message_graph.add_conditional_edges("save_message", response_or_not)
new_message_graph.add_edge("plan", "execute_plans")
new_message_graph.add_edge("execute_plans", "generate_response")
new_message_graph.add_edge("generate_response", "evaluate_response")

def route_based_on_evaluation(state: NewMessageGraphState) -> str:
    if state.latest_evaluation_feedback == "plan_again":
        return "plan"
    elif state.latest_evaluation_feedback == "execute_again":
        return "execute_plans"
    elif state.latest_evaluation_feedback == "generate_again":
        return "generate_response"
    elif state.latest_evaluation_feedback == "finalize":
        return END
    else:
        return START

new_message_graph.add_conditional_edges("evaluate_response", route_based_on_evaluation)
