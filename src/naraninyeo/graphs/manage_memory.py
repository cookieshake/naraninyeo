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
    state: ManageMemoryGraphState,
    runtime: Runtime[ManageMemoryGraphContext],
    messages: list[Message],
    existing_memories: list[MemoryItem],
) -> list[MemoryItem]:
    id_generator = runtime.context.id_generator
    existing_contents = [m.content for m in existing_memories]
    memories = await memory_extractor.run_with_generator(
        MemoryExtractorDeps(latest_messages=messages, existing_memories=existing_contents)
    )
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
    existing = await repo.get_channel_memory_items(
        state.current_tctx, state.current_bot.bot_id, state.incoming_message.channel.channel_id
    )
    memory_items = await _extract_memory_items(
        state, runtime, state.latest_history + [state.incoming_message], list(existing)
    )
    await repo.upsert_many(state.current_tctx, memory_items)
    return state


# ---------------------------------------------------------------------------
# Node: manage_memory
# ---------------------------------------------------------------------------


async def _prune_memories(
    state: ManageMemoryGraphState,
    runtime: Runtime[ManageMemoryGraphContext],
    memories: list[MemoryItem],
    kind: Literal["short_term", "long_term"],
) -> list[MemoryItem]:
    now = runtime.context.clock.now()
    pruned_memories = []
    prune_actions = await memory_pruner.run_with_generator(MemoryPrunerDeps(memories=memories))

    # pruner uses 1-indexed int IDs matching the position in the memories list
    id_map = {i + 1: m.memory_id for i, m in enumerate(memories)}
    memory_ids_to_delete: set[str] = set()

    for action in prune_actions.output:
        resolved_ids = [id_map[i] for i in action.ids if i in id_map]
        if action.method == "delete":
            memory_ids_to_delete.update(resolved_ids)
        elif action.method == "merge":
            source_memories = [m for m in memories if m.memory_id in resolved_ids]
            expires_at = None if kind == "long_term" else now + timedelta(days=7)
            merged_memory = MemoryItem(
                memory_id=runtime.context.id_generator.generate_id(),
                bot_id=state.current_bot.bot_id,
                channel_id=state.incoming_message.channel.channel_id,
                kind=kind,
                content=action.merged_content,
                created_at=min((m.created_at for m in source_memories), default=now),
                updated_at=now,
                expires_at=expires_at,
            )
            pruned_memories.append(merged_memory)
            memory_ids_to_delete.update(resolved_ids)

    remaining = [m for m in memories if m.memory_id not in memory_ids_to_delete]
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
    modified_ids: set[str] = set()

    # Prune short-term memories if too many accumulated
    if len(short_term) > 50:
        short_term = await _prune_memories(state, runtime, short_term, kind="short_term")

    # Promote old short-term memories to long-term when threshold is reached
    old_short_term = [m for m in short_term if (now - m.created_at).days > 4]
    if len(old_short_term) > 15:
        promoted = [m.model_copy(update={"kind": "long_term", "expires_at": None}) for m in old_short_term]
        modified_ids.update(m.memory_id for m in promoted)
        old_ids = {m.memory_id for m in old_short_term}
        short_term = [m for m in short_term if m.memory_id not in old_ids]
        long_term.extend(promoted)

    # Prune long-term memories if too many accumulated
    if len(long_term) > 50:
        long_term = await _prune_memories(state, runtime, long_term, kind="long_term")

    # Persist the consolidated memory set — only upsert changed/new items
    new_memories = short_term + long_term
    existing_ids = {m.memory_id for m in all_memories}
    stale_ids = [m.memory_id for m in all_memories if m.memory_id not in {nm.memory_id for nm in new_memories}]
    changed_memories = [m for m in new_memories if m.memory_id not in existing_ids or m.memory_id in modified_ids]
    if stale_ids:
        await repo.delete_many(tctx, stale_ids)
    if changed_memories:
        await repo.upsert_many(tctx, changed_memories)
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
