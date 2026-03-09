"""Memory management graph.

Pipeline: add_memory → manage_memory
Extracts new memories from recent messages, then prunes/consolidates existing ones.
"""

from datetime import timedelta
from typing import List, Literal, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict

from naraninyeo.agents.memory_extractor import MemoryExtractorDeps, memory_extractor
from naraninyeo.agents.memory_pruner import MemoryPrunerDeps, memory_pruner
from naraninyeo.core.interfaces import Clock, IdGenerator, MemoryRepository
from naraninyeo.core.models import Bot, MemoryItem, Message, TenancyContext

# ---------------------------------------------------------------------------
# State & Context
# ---------------------------------------------------------------------------


class ManageMemoryGraphState(BaseModel):
    current_tctx: TenancyContext
    current_bot: Bot
    status: Literal["processing", "completed", "failed"]
    incoming_message: Message
    latest_history: Optional[List[Message]] = None


class ManageMemoryGraphContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    clock: Clock
    id_generator: IdGenerator
    memory_repository: MemoryRepository


# ---------------------------------------------------------------------------
# Node: add_memory
# ---------------------------------------------------------------------------


async def _extract_memory_items(
    state: ManageMemoryGraphState, runtime: Runtime[ManageMemoryGraphContext], messages: list[Message]
) -> list[MemoryItem]:
    id_generator = runtime.context.id_generator
    memories = await memory_extractor.run_with_generator(MemoryExtractorDeps(latest_messages=messages))
    now = state.incoming_message.timestamp
    return [
        MemoryItem(
            memory_id=id_generator.generate_id(),
            bot_id=state.current_bot.bot_id,
            channel_id=state.incoming_message.channel.channel_id,
            kind="short_term",
            content=memory,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=7),
        )
        for memory in memories.output
    ]


async def add_memory(
    state: ManageMemoryGraphState, runtime: Runtime[ManageMemoryGraphContext]
) -> ManageMemoryGraphState:
    if not state.latest_history:
        return state

    repo = runtime.context.memory_repository
    memory_items = await _extract_memory_items(state, runtime, state.latest_history + [state.incoming_message])
    await repo.upsert_many(state.current_tctx, memory_items)
    return state


# ---------------------------------------------------------------------------
# Node: manage_memory
# ---------------------------------------------------------------------------


async def _prune_memories(
    state: ManageMemoryGraphState,
    runtime: Runtime[ManageMemoryGraphContext],
    memories: list[MemoryItem],
    retention_days: int,
    kind: Literal["short_term", "long_term"],
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
                kind=kind,
                content=action.merged_content,
                created_at=max([memory.created_at for memory in memories if memory.memory_id in action.ids]),
                updated_at=now,
                expires_at=now + timedelta(days=retention_days),
            )
            pruned_memories.append(merged_memory)
            memory_ids_to_delete.extend(action.ids)

    remaining = [memory for memory in memories if memory.memory_id not in memory_ids_to_delete]
    return remaining + pruned_memories


async def manage_memory(
    state: ManageMemoryGraphState, runtime: Runtime[ManageMemoryGraphContext]
) -> ManageMemoryGraphState:
    tctx = state.current_tctx
    repo = runtime.context.memory_repository
    now = runtime.context.clock.now()

    all_memories = await repo.get_channel_memory_items(
        tctx, state.current_bot.bot_id, state.incoming_message.channel.channel_id, limit=500
    )

    short_term = [m for m in all_memories if m.kind == "short_term"]
    long_term = [m for m in all_memories if m.kind == "long_term"]

    # Prune short-term memories if too many accumulated
    if len(short_term) > 100:
        short_term = await _prune_memories(state, runtime, short_term, retention_days=7, kind="short_term")

    # Promote old short-term memories to long-term when threshold is reached
    old_short_term = [m for m in short_term if (now - m.created_at).days > 4]
    if len(old_short_term) > 30:
        promoted = await _prune_memories(state, runtime, old_short_term, retention_days=60, kind="long_term")
        old_ids = {m.memory_id for m in old_short_term}
        short_term = [m for m in short_term if m.memory_id not in old_ids]
        long_term.extend(promoted)

    # Prune long-term memories if too many accumulated
    if len(long_term) > 100:
        long_term = await _prune_memories(state, runtime, long_term, retention_days=60, kind="long_term")

    # Persist the consolidated memory set
    new_memories = short_term + long_term
    stale_ids = [m.memory_id for m in all_memories if m.memory_id not in {nm.memory_id for nm in new_memories}]
    await repo.delete_many(tctx, stale_ids)
    await repo.upsert_many(tctx, new_memories)
    await repo.delete_expired(tctx, now)

    return state


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

_graph = StateGraph(state_schema=ManageMemoryGraphState, context_schema=ManageMemoryGraphContext)

_graph.add_node("add_memory", add_memory)
_graph.add_node("manage_memory", manage_memory)

_graph.add_edge(START, "add_memory")
_graph.add_edge("add_memory", "manage_memory")
_graph.add_edge("manage_memory", END)

manage_memory_graph = _graph.compile()
