"""
메모리 관리 그래프 행동 스펙 테스트

스펙:
- 대화 이력이 있으면 메모리 추출 후 DB에 저장
- 저장된 메모리의 kind="short_term", expires_at은 미래
- 대화 이력이 없으면 메모리 추출 미실행
- old short_term 기억이 30개 초과 시 long_term으로 승격
연동: 실제 LLM (memory_extractor) + testcontainer DB
"""

from datetime import UTC, datetime, timedelta

import pytest
from dishka import AsyncContainer

from naraninyeo.core.interfaces import Clock, IdGenerator, MemoryRepository
from naraninyeo.core.models import (
    Author,
    Bot,
    Channel,
    MemoryItem,
    Message,
    MessageContent,
    TenancyContext,
)
from naraninyeo.graphs.manage_memory import (
    ManageMemoryGraphContext,
    ManageMemoryGraphState,
    manage_memory_graph,
)
from naraninyeo.infrastructure.util.nanoid_generator import NanoidGenerator


def _nanoid() -> str:
    return NanoidGenerator().generate_id()


def _make_message(text: str, channel_id: str = "ch-mem-test") -> Message:
    return Message(
        message_id=_nanoid(),
        channel=Channel(channel_id=channel_id, channel_name="테스트채널"),
        author=Author(author_id="user-1", author_name="테스터"),
        content=MessageContent(text=text),
        timestamp=datetime.now(UTC),
    )


def _make_bot() -> Bot:
    return Bot(
        bot_id=_nanoid(),
        bot_name="메모리테스트봇",
        author_id="author-1",
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_add_memory_with_history_stores_memories(test_container: AsyncContainer):
    """대화 이력이 있으면 메모리가 추출되어 DB에 저장된다."""
    memory_repo = await test_container.get(MemoryRepository)
    clock = await test_container.get(Clock)
    id_generator = await test_container.get(IdGenerator)

    tctx = TenancyContext(tenant_id="test-mem-tenant")
    bot = _make_bot()
    channel_id = _nanoid()

    history = [
        _make_message("나는 파이썬 개발자야", channel_id=channel_id),
        _make_message("서울에 살고 있어", channel_id=channel_id),
    ]
    incoming = _make_message("잘 기억해줘", channel_id=channel_id)

    state = ManageMemoryGraphState(
        current_tctx=tctx,
        current_bot=bot,
        status="processing",
        incoming_message=incoming,
        latest_history=history,
    )
    graph_context = ManageMemoryGraphContext(
        clock=clock,
        id_generator=id_generator,
        memory_repository=memory_repo,
    )

    await manage_memory_graph.ainvoke(state, context=graph_context)

    stored = await memory_repo.get_channel_memory_items(tctx, bot.bot_id, channel_id)
    assert len(stored) > 0, "메모리가 저장되지 않음"


@pytest.mark.asyncio
async def test_stored_memories_are_short_term_with_future_expiry(test_container: AsyncContainer):
    """저장된 메모리는 kind='short_term'이고 expires_at이 미래 시점이다."""
    memory_repo = await test_container.get(MemoryRepository)
    clock = await test_container.get(Clock)
    id_generator = await test_container.get(IdGenerator)

    tctx = TenancyContext(tenant_id="test-mem-tenant-2")
    bot = _make_bot()
    channel_id = _nanoid()

    history = [_make_message("내 이름은 홍길동이야", channel_id=channel_id)]
    incoming = _make_message("기억해", channel_id=channel_id)

    state = ManageMemoryGraphState(
        current_tctx=tctx,
        current_bot=bot,
        status="processing",
        incoming_message=incoming,
        latest_history=history,
    )
    graph_context = ManageMemoryGraphContext(
        clock=clock,
        id_generator=id_generator,
        memory_repository=memory_repo,
    )

    await manage_memory_graph.ainvoke(state, context=graph_context)

    stored = await memory_repo.get_channel_memory_items(tctx, bot.bot_id, channel_id)
    now = datetime.now(UTC)
    for mem in stored:
        assert mem.kind == "short_term", f"kind가 short_term이 아님: {mem.kind}"
        if mem.expires_at:
            assert mem.expires_at > now, f"expires_at이 과거: {mem.expires_at}"


@pytest.mark.asyncio
async def test_add_memory_without_history_stores_nothing(test_container: AsyncContainer):
    """대화 이력이 없으면 메모리가 저장되지 않는다."""
    memory_repo = await test_container.get(MemoryRepository)
    clock = await test_container.get(Clock)
    id_generator = await test_container.get(IdGenerator)

    tctx = TenancyContext(tenant_id="test-mem-tenant-3")
    bot = _make_bot()
    channel_id = _nanoid()
    incoming = _make_message("테스트 메시지", channel_id=channel_id)

    state = ManageMemoryGraphState(
        current_tctx=tctx,
        current_bot=bot,
        status="processing",
        incoming_message=incoming,
        latest_history=None,  # 이력 없음
    )
    graph_context = ManageMemoryGraphContext(
        clock=clock,
        id_generator=id_generator,
        memory_repository=memory_repo,
    )

    await manage_memory_graph.ainvoke(state, context=graph_context)

    stored = await memory_repo.get_channel_memory_items(tctx, bot.bot_id, channel_id)
    assert len(stored) == 0, f"이력이 없는데 메모리가 저장됨: {stored}"


@pytest.mark.asyncio
async def test_old_short_term_memories_promoted_to_long_term(test_container: AsyncContainer):
    """4일 이상 된 short_term 기억이 31개 이상이면 long_term으로 승격된다."""
    memory_repo = await test_container.get(MemoryRepository)
    clock = await test_container.get(Clock)
    id_generator = await test_container.get(IdGenerator)

    tctx = TenancyContext(tenant_id="test-mem-tenant-4")
    bot = _make_bot()
    channel_id = _nanoid()

    # 5일 전 생성된 short_term 기억 31개 직접 삽입
    old_time = datetime.now(UTC) - timedelta(days=5)
    old_memories = []
    for i in range(31):
        mem_id = _nanoid()
        old_memories.append(
            MemoryItem(
                memory_id=mem_id,
                bot_id=bot.bot_id,
                channel_id=channel_id,
                kind="short_term",
                content=f"오래된 기억 {i}",
                created_at=old_time,
                updated_at=old_time,
                expires_at=old_time + timedelta(days=7),
            )
        )
    await memory_repo.upsert_many(tctx, old_memories)

    incoming = _make_message("테스트", channel_id=channel_id)
    state = ManageMemoryGraphState(
        current_tctx=tctx,
        current_bot=bot,
        status="processing",
        incoming_message=incoming,
        latest_history=None,
    )
    graph_context = ManageMemoryGraphContext(
        clock=clock,
        id_generator=id_generator,
        memory_repository=memory_repo,
    )

    await manage_memory_graph.ainvoke(state, context=graph_context)

    stored = await memory_repo.get_channel_memory_items(tctx, bot.bot_id, channel_id, limit=500)
    long_term = [m for m in stored if m.kind == "long_term"]
    assert len(long_term) > 0, "승격된 long_term 기억이 없음"
