
from typing import List, Optional
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END

from naraninyeo.core.models import Message

class NewMessageGraphState(BaseModel):
    incomming_message: Optional[Message] = None
    latest_history: Optional[List[Message]] = None
    retrieved_contexts: Optional[List[RetrievedContext]] = None
    bot_responses: Optional[List[BotResponse]] = None

new_message_graph = StateGraph(NewMessageGraphState)

new_message_graph.add_node(save_message)
new_message_graph.add_node(add_memory)
new_message_graph.add_node(manage_memory)
new_message_graph.add_node(plan)
new_message_graph.add_node(execute_plans)
new_message_graph.add_node(generate_response)
new_message_graph.add_node(evaluate_response)
new_message_graph.add_node(finalize_response)


def response_or_not(state: NewMessageGraphState) -> str:
    if state.incomming_message and state.incomming_message.content.text.strip():
        return "response"
    else:
        return END

new_message_graph.add_conditional_edges(
    START,
    [
        (lambda state: state.incomming_message is not None, save_message),
    ],
)