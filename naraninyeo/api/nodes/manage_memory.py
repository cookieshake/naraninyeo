from langgraph.runtime import Runtime

from naraninyeo.api.graphs.new_message import NewMessageGraphContext, NewMessageGraphState
from naraninyeo.core.models import MemoryItem


async def select_memory_to_prune(
    memory_items: list[MemoryItem]
) -> list[MemoryItem]:
    # Placeholder logic for selecting memory items to prune
    return []

async def manage_memory(
    state: NewMessageGraphState,
    runtime: Runtime[NewMessageGraphContext]
) -> NewMessageGraphState:
    repo = runtime.context.memory_repository
    await repo.delete_expired(runtime.context.clock.now())

    memories = await repo.get_channel_memory_items(
        bot_id=state.current_bot.author_id,
        channel_id=state.incoming_message.channel.channel_id
    )

    memories_to_prune = await select_memory_to_prune(list(memories))
    if memories_to_prune:
        memory_ids_to_prune = [memory.memory_id for memory in memories_to_prune]
        await repo.delete_many(memory_ids_to_prune)

    return state
