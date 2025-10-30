from datetime import timedelta

from langgraph.runtime import Runtime

from naraninyeo.api.agents.memory_extractor import MemoryExtractorDeps, memory_extractor
from naraninyeo.api.graphs.manage_memory.models import ManageMemoryGraphContext, ManageMemoryGraphState
from naraninyeo.core.models import MemoryItem, Message


async def extract_memory_items_from_messages(
    state: ManageMemoryGraphState,
    runtime: Runtime[ManageMemoryGraphContext],
    messages: list[Message]
) -> list[MemoryItem]:
    clock = runtime.context.clock
    id_generator = runtime.context.id_generator
    memories = await memory_extractor.run_with_generator(
        MemoryExtractorDeps(latest_messages=messages)
    )
    now = clock.now()
    memories = [
        MemoryItem(
            memory_id=id_generator.generate_id(),
            bot_id=state.current_bot.bot_id,
            channel_id=state.incoming_message.channel.channel_id,
            kind="short_term",
            content=memory,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=7)
        )
        for memory in memories.output
    ]
    return memories



async def add_memory(
    state: ManageMemoryGraphState,
    runtime: Runtime[ManageMemoryGraphContext]
) -> ManageMemoryGraphState:
    repo = runtime.context.memory_repository
    if not state.latest_history:
        return state

    memory_items = await extract_memory_items_from_messages(
        state,
        runtime,
        state.latest_history + [state.incoming_message]
    )
    await repo.upsert_many(state.current_tctx, memory_items)

    return state
