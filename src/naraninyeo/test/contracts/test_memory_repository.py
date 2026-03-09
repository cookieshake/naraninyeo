"""
MemoryRepository 계약 테스트

스펙: core/interfaces.py MemoryRepository Protocol
구현체: infrastructure/repository/memory.py VchordMemoryRepository
연동: testcontainer PostgreSQL
"""

from datetime import UTC, datetime, timedelta

import pytest

from naraninyeo.core.interfaces import MemoryRepository
from naraninyeo.core.models import TenancyContext


@pytest.mark.asyncio
async def test_upsert_and_get_returns_memory_items(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item
):
    """upsert_many 후 get_channel_memory_items로 조회 가능하다."""
    item = make_memory_item(bot_id="bot-mem-1", channel_id="ch-mem-1")
    await memory_repository.upsert_many(default_tctx, [item])

    results = await memory_repository.get_channel_memory_items(default_tctx, "bot-mem-1", "ch-mem-1")
    memory_ids = {r.memory_id for r in results}

    assert item.memory_id in memory_ids


@pytest.mark.asyncio
async def test_upsert_is_idempotent(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item
):
    """동일 ID를 두 번 upsert하면 덮어쓴다 (중복 없음)."""
    item = make_memory_item(bot_id="bot-mem-2", channel_id="ch-mem-2", content="원본")
    await memory_repository.upsert_many(default_tctx, [item])

    updated = item.model_copy(update={"content": "수정됨"})
    await memory_repository.upsert_many(default_tctx, [updated])

    results = await memory_repository.get_channel_memory_items(default_tctx, "bot-mem-2", "ch-mem-2")
    matching = [r for r in results if r.memory_id == item.memory_id]

    assert len(matching) == 1
    assert matching[0].content == "수정됨"


@pytest.mark.asyncio
async def test_delete_many_removes_items_and_returns_count(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item
):
    """delete_many는 지정 ID를 삭제하고 삭제 건수를 반환한다."""
    item1 = make_memory_item(bot_id="bot-mem-3", channel_id="ch-mem-3")
    item2 = make_memory_item(bot_id="bot-mem-3", channel_id="ch-mem-3")
    await memory_repository.upsert_many(default_tctx, [item1, item2])

    deleted_count = await memory_repository.delete_many(default_tctx, [item1.memory_id])

    assert deleted_count == 1
    results = await memory_repository.get_channel_memory_items(default_tctx, "bot-mem-3", "ch-mem-3")
    ids = {r.memory_id for r in results}
    assert item1.memory_id not in ids
    assert item2.memory_id in ids


@pytest.mark.asyncio
async def test_delete_expired_removes_only_expired_items(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item
):
    """delete_expired는 expires_at이 current_time 이전인 항목만 삭제한다."""
    past = datetime.now(UTC) - timedelta(days=1)
    future = datetime.now(UTC) + timedelta(days=7)

    expired_item = make_memory_item(bot_id="bot-mem-4", channel_id="ch-mem-4", expires_at=past)
    valid_item = make_memory_item(bot_id="bot-mem-4", channel_id="ch-mem-4", expires_at=future)
    await memory_repository.upsert_many(default_tctx, [expired_item, valid_item])

    await memory_repository.delete_expired(default_tctx, datetime.now(UTC))

    results = await memory_repository.get_channel_memory_items(default_tctx, "bot-mem-4", "ch-mem-4")
    ids = {r.memory_id for r in results}
    assert expired_item.memory_id not in ids
    assert valid_item.memory_id in ids


@pytest.mark.asyncio
async def test_get_latest_memory_update_ts_returns_most_recent(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item
):
    """get_latest_memory_update_ts는 가장 최근 updated_at을 반환한다."""
    item1 = make_memory_item(bot_id="bot-mem-5", channel_id="ch-mem-5")
    item2 = make_memory_item(bot_id="bot-mem-5", channel_id="ch-mem-5")
    await memory_repository.upsert_many(default_tctx, [item1, item2])

    ts = await memory_repository.get_latest_memory_update_ts(default_tctx, "bot-mem-5", "ch-mem-5")

    assert ts is not None
    expected_max = max(item1.updated_at, item2.updated_at)
    assert abs((ts - expected_max).total_seconds()) < 1


@pytest.mark.asyncio
async def test_get_latest_memory_update_ts_returns_none_when_empty(
    memory_repository: MemoryRepository, default_tctx: TenancyContext
):
    """메모리가 없으면 None을 반환한다."""
    ts = await memory_repository.get_latest_memory_update_ts(default_tctx, "bot-no-mem", "ch-no-mem")

    assert ts is None


@pytest.mark.asyncio
async def test_get_channel_memory_items_respects_limit(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item
):
    """get_channel_memory_items는 limit을 준수한다."""
    items = [make_memory_item(bot_id="bot-mem-6", channel_id="ch-mem-6") for _ in range(5)]
    await memory_repository.upsert_many(default_tctx, items)

    results = await memory_repository.get_channel_memory_items(default_tctx, "bot-mem-6", "ch-mem-6", limit=3)

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_get_channel_memory_items_ordered_by_updated_at_desc(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item
):
    """get_channel_memory_items는 updated_at 내림차순으로 정렬된다."""
    from datetime import timedelta

    now = datetime.now(UTC)
    item_old = make_memory_item(bot_id="bot-mem-7", channel_id="ch-mem-7")
    item_old = item_old.model_copy(update={"updated_at": now - timedelta(hours=1)})
    item_new = make_memory_item(bot_id="bot-mem-7", channel_id="ch-mem-7")
    item_new = item_new.model_copy(update={"updated_at": now})

    await memory_repository.upsert_many(default_tctx, [item_old, item_new])

    results = await memory_repository.get_channel_memory_items(default_tctx, "bot-mem-7", "ch-mem-7")

    if len(results) >= 2:
        assert results[0].updated_at >= results[1].updated_at


@pytest.mark.asyncio
async def test_search_memories_returns_relevant_items(
    memory_repository: MemoryRepository, default_tctx: TenancyContext, make_memory_item, text_embedder
):
    """search_memories는 쿼리 임베딩 기반으로 기억을 반환한다."""
    item = make_memory_item(bot_id="bot-mem-8", channel_id="ch-mem-8", content="파이썬 개발자입니다")
    await memory_repository.upsert_many(default_tctx, [item])

    query_emb = await text_embedder.embed_queries(["파이썬"])
    results = await memory_repository.search_memories(
        default_tctx, "bot-mem-8", "ch-mem-8", query_emb[0], limit=10
    )

    ids = {r.memory_id for r in results}
    assert item.memory_id in ids
