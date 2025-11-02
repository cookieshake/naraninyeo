from typing import List, Literal, Optional

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from naraninyeo.api.graphs.manage_memory.add_memory import add_memory
from naraninyeo.api.graphs.manage_memory.manage_memory import manage_memory
from naraninyeo.api.graphs.manage_memory.models import ManageMemoryGraphContext, ManageMemoryGraphState

_manage_memory_graph = StateGraph(
    state_schema=ManageMemoryGraphState, context_schema=ManageMemoryGraphContext
)

_manage_memory_graph.add_node("add_memory", add_memory)
_manage_memory_graph.add_node("manage_memory", manage_memory)

_manage_memory_graph.add_edge(START, "add_memory")
_manage_memory_graph.add_edge("add_memory", "manage_memory")
_manage_memory_graph.add_edge("manage_memory", END)

manage_memory_graph = _manage_memory_graph.compile()
