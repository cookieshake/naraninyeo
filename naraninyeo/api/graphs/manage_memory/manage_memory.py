from datetime import timedelta
from typing import Literal

from langgraph.runtime import Runtime

from naraninyeo.api.agents.memory_pruner import MemoryPrunerDeps, memory_pruner
from naraninyeo.api.graphs.manage_memory.models import ManageMemoryGraphContext, ManageMemoryGraphState
from naraninyeo.core.models import MemoryItem


async def prune_memories(
    state: ManageMemoryGraphState,
    runtime: Runtime[ManageMemoryGraphContext],
    memories: list[MemoryItem],
    new_memory_retention_days: int,
    new_memory_kind: Literal["short_term", "long_term"],
) -> list[MemoryItem]:
    now = runtime.context.clock.now()
    pruned_memories = []
    prune_actions = await memory_pruner.run_with_generator(MemoryPrunerDeps(memories=memories))
    memory_ids_to_delete = []
    for action in prune_actions.output:
        if action.method == "delete":
            memory_ids_to_delete.extend(action.ids)
        elif action.method == "merge":
            merged_memory = MemoryItem(
                memory_id=runtime.context.id_generator.generate_id(),
                bot_id=state.current_bot.bot_id,
                channel_id=state.incoming_message.channel.channel_id,
                kind=new_memory_kind,
                content=action.merged_content,
                created_at=max([memory.created_at for memory in memories if memory.memory_id in action.ids]),
                updated_at=now,
                expires_at=now + timedelta(days=new_memory_retention_days),
            )
            pruned_memories.append(merged_memory)
            memory_ids_to_delete.extend(action.ids)
    memories[:] = [memory for memory in memories if memory.memory_id not in memory_ids_to_delete]
    return memories + pruned_memories


async def prune_short_term_memories(
    state: ManageMemoryGraphState, runtime: Runtime[ManageMemoryGraphContext], short_memories: list[MemoryItem]
) -> list[MemoryItem]:
    pruned_memories = await prune_memories(
        state, runtime, short_memories, new_memory_retention_days=7, new_memory_kind="short_term"
    )
    return pruned_memories


async def prune_long_term_memories(
    state: ManageMemoryGraphState, runtime: Runtime[ManageMemoryGraphContext], long_memories: list[MemoryItem]
) -> list[MemoryItem]:
    pruned_memories = await prune_memories(
        state, runtime, long_memories, new_memory_retention_days=60, new_memory_kind="long_term"
    )
    return pruned_memories


async def manage_memory(
    state: ManageMemoryGraphState, runtime: Runtime[ManageMemoryGraphContext]
) -> ManageMemoryGraphState:
    tctx = state.current_tctx
    repo = runtime.context.memory_repository

    memories = await repo.get_channel_memory_items(
        tctx, state.current_bot.bot_id, state.incoming_message.channel.channel_id, limit=500
    )
    short_term_memories = [memory for memory in memories if memory.kind == "short_term"]
    if len(short_term_memories) > 100:
        short_term_memories = await prune_short_term_memories(state, runtime, short_term_memories)
    old_short_memories = [m for m in short_term_memories if (runtime.context.clock.now() - m.created_at).days > 4]
    if len(old_short_memories) > 30:
        promoted_short_memories = await prune_short_term_memories(state, runtime, short_term_memories)
        short_term_memories = [
            m for m in short_term_memories if m.memory_id not in {pm.memory_id for pm in promoted_short_memories}
        ]

    long_term_memories = [memory for memory in memories if memory.kind == "long_term"]
    if len(long_term_memories) > 100:
        long_term_memories = await prune_long_term_memories(state, runtime, long_term_memories)

    new_memories = short_term_memories + long_term_memories
    await repo.delete_many(
        tctx, [memory.memory_id for memory in memories if memory.memory_id not in {nm.memory_id for nm in new_memories}]
    )
    await repo.upsert_many(tctx, new_memories)
    await repo.delete_expired(tctx, runtime.context.clock.now())
    return state
