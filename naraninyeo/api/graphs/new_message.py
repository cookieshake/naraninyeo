
from typing import List, Optional, Literal

from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END

from naraninyeo.api.infrastructure.interfaces import Clock, MessageRepository
from naraninyeo.core.models import Message

class NewMessageGraphState(BaseModel):
    incomming_message: Optional[Message] = None
    latest_history: Optional[List[Message]] = None
    retrieved_contexts: Optional[List[RetrievedContext]] = None
    bot_responses: Optional[List[BotResponse]] = None
    latest_evaluation_feedback: Optional[
        Literal["plan_again", "execute_again", "generate_again", "finalize"]
    ] = None

class NewMessageGraphContext(BaseModel):
    clock: Clock
    message_repository: MessageRepository

new_message_graph = StateGraph(NewMessageGraphState)

new_message_graph.add_node(save_message)
new_message_graph.add_node(add_memory)
new_message_graph.add_node(manage_memory)
new_message_graph.add_node(plan)
new_message_graph.add_node(execute_plans)
new_message_graph.add_node(generate_response)
new_message_graph.add_node(evaluate_response)
new_message_graph.add_node(finalize_response)

new_message_graph.set_entry_point("save_message")
new_message_graph.add_edge("save_message", "add_memory")

def response_or_not(state: NewMessageGraphState) -> str:
    if state.incomming_message and state.incomming_message.content.text.strip():
        return "plan"
    else:
        return END

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


