from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState
from naraninyeo.core.models import MemoryItem, Message


async def extract_memory_items_from_messages(
    messages: list[Message]
) -> list[MemoryItem]:
    ...

async def add_memory(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    repo = runtime.context.memory_repository
    if not state.latest_history:
        return state

    memory_items = await extract_memory_items_from_messages(state.latest_history)
    await repo.create_many(memory_items)

    return state
