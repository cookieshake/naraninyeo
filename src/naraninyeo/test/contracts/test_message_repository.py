"""
MessageRepository 계약 테스트

스펙: core/interfaces.py MessageRepository Protocol
구현체: infrastructure/repository/message.py VchordMessageRepository
연동: testcontainer PostgreSQL + testcontainer llama.cpp (임베딩)
"""

from datetime import UTC, datetime, timedelta

import pytest

from naraninyeo.core.interfaces import MessageRepository
from naraninyeo.core.models import TenancyContext


@pytest.mark.asyncio
async def test_upsert_and_get_before_returns_message(
    message_repository: MessageRepository, default_tctx: TenancyContext, make_message
):
    """upsert 후 get_channel_messages_before로 조회 가능하다."""
    now = datetime.now(UTC)
    msg = make_message(channel_id="ch-msg-1", timestamp=now - timedelta(seconds=1))
    anchor = make_message(channel_id="ch-msg-1", timestamp=now)
    await message_repository.upsert(default_tctx, msg)
    await message_repository.upsert(default_tctx, anchor)

    results = await message_repository.get_channel_messages_before(
        default_tctx, "ch-msg-1", anchor.message_id, limit=10
    )
    ids = {m.message_id for m in results}

    assert msg.message_id in ids


@pytest.mark.asyncio
async def test_upsert_is_idempotent(message_repository: MessageRepository, default_tctx: TenancyContext, make_message):
    """동일 message_id를 두 번 upsert해도 중복 없이 덮어쓴다."""
    now = datetime.now(UTC)
    msg = make_message(channel_id="ch-msg-2", text="원본", timestamp=now - timedelta(seconds=1))
    anchor = make_message(channel_id="ch-msg-2", timestamp=now)
    await message_repository.upsert(default_tctx, msg)
    await message_repository.upsert(default_tctx, anchor)

    updated = msg.model_copy(update={"content": msg.content.model_copy(update={"text": "수정됨"})})
    await message_repository.upsert(default_tctx, updated)

    results = await message_repository.get_channel_messages_before(default_tctx, "ch-msg-2", anchor.message_id, limit=10)
    matching = [m for m in results if m.message_id == msg.message_id]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_get_channel_messages_before_respects_limit(
    message_repository: MessageRepository, default_tctx: TenancyContext, make_message
):
    """get_channel_messages_before는 limit을 준수한다."""
    now = datetime.now(UTC)
    msgs = [make_message(channel_id="ch-msg-3", timestamp=now - timedelta(seconds=i + 1)) for i in range(5)]
    anchor = make_message(channel_id="ch-msg-3", timestamp=now)
    for m in msgs:
        await message_repository.upsert(default_tctx, m)
    await message_repository.upsert(default_tctx, anchor)

    results = await message_repository.get_channel_messages_before(default_tctx, "ch-msg-3", anchor.message_id, limit=3)

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_get_channel_messages_after_returns_later_messages(
    message_repository: MessageRepository, default_tctx: TenancyContext, make_message
):
    """get_channel_messages_after는 anchor 이후 메시지를 반환한다."""
    now = datetime.now(UTC)
    anchor = make_message(channel_id="ch-msg-4", timestamp=now - timedelta(seconds=2))
    later = make_message(channel_id="ch-msg-4", timestamp=now - timedelta(seconds=1))
    await message_repository.upsert(default_tctx, anchor)
    await message_repository.upsert(default_tctx, later)

    results = await message_repository.get_channel_messages_after(default_tctx, "ch-msg-4", anchor.message_id, limit=10)
    ids = {m.message_id for m in results}

    assert later.message_id in ids
    assert anchor.message_id not in ids


@pytest.mark.asyncio
async def test_text_search_messages_finds_relevant_messages(
    message_repository: MessageRepository, default_tctx: TenancyContext, make_message
):
    """text_search_messages는 검색어 관련 메시지를 반환한다."""
    relevant = make_message(channel_id="ch-msg-5", text="삼성전자 주가 정보가 궁금합니다")
    irrelevant = make_message(channel_id="ch-msg-5", text="오늘 점심 뭐 먹을까요")
    await message_repository.upsert(default_tctx, relevant)
    await message_repository.upsert(default_tctx, irrelevant)

    results = await message_repository.text_search_messages(default_tctx, "ch-msg-5", "삼성전자 주가", limit=5)

    ids = {m.message_id for m in results}
    assert relevant.message_id in ids


@pytest.mark.asyncio
async def test_tenant_isolation_in_messages(message_repository: MessageRepository, make_message):
    """다른 tenant의 메시지는 조회되지 않는다."""
    tenant_a = TenancyContext(tenant_id="tenant-msg-a")
    tenant_b = TenancyContext(tenant_id="tenant-msg-b")

    msg = make_message(channel_id="ch-isolated")
    await message_repository.upsert(tenant_a, msg)

    results = await message_repository.get_channel_messages_before(tenant_b, "ch-isolated", "z" * 21, limit=10)
    ids = {m.message_id for m in results}
    assert msg.message_id not in ids
