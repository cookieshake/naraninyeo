"""
BotRepository 계약 테스트

스펙: core/interfaces.py BotRepository Protocol
구현체: infrastructure/repository/bot.py VchordBotRepository
연동: testcontainer PostgreSQL
"""

import pytest

from naraninyeo.core.interfaces import BotRepository
from naraninyeo.core.models import TenancyContext


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_bot(bot_repository: BotRepository, default_tctx: TenancyContext):
    """존재하지 않는 bot_id 조회 시 None을 반환한다."""
    result = await bot_repository.get(default_tctx, "non-existent-bot-id")

    assert result is None


@pytest.mark.asyncio
async def test_create_and_get_returns_same_bot(bot_repository: BotRepository, default_tctx: TenancyContext, make_bot):
    """create 후 get하면 동일한 bot을 반환한다."""
    bot = make_bot()
    await bot_repository.create(default_tctx, bot)

    result = await bot_repository.get(default_tctx, bot.bot_id)

    assert result is not None
    assert result.bot_id == bot.bot_id
    assert result.bot_name == bot.bot_name
    assert result.author_id == bot.author_id


@pytest.mark.asyncio
async def test_list_all_includes_created_bots(bot_repository: BotRepository, default_tctx: TenancyContext, make_bot):
    """create한 봇들이 list_all 결과에 포함된다."""
    bot1 = make_bot(bot_name="봇1")
    bot2 = make_bot(bot_name="봇2")
    await bot_repository.create(default_tctx, bot1)
    await bot_repository.create(default_tctx, bot2)

    all_bots = await bot_repository.list_all(default_tctx)
    bot_ids = {b.bot_id for b in all_bots}

    assert bot1.bot_id in bot_ids
    assert bot2.bot_id in bot_ids


@pytest.mark.asyncio
async def test_tenant_isolation(bot_repository: BotRepository, make_bot):
    """다른 tenant의 봇은 조회되지 않는다."""
    tenant_a = TenancyContext(tenant_id="tenant-a")
    tenant_b = TenancyContext(tenant_id="tenant-b")

    bot = make_bot()
    await bot_repository.create(tenant_a, bot)

    result = await bot_repository.get(tenant_b, bot.bot_id)
    assert result is None

    all_bots_b = await bot_repository.list_all(tenant_b)
    assert not any(b.bot_id == bot.bot_id for b in all_bots_b)


@pytest.mark.asyncio
async def test_list_all_returns_sequence(bot_repository: BotRepository, default_tctx: TenancyContext):
    """list_all은 시퀀스 타입을 반환한다."""
    result = await bot_repository.list_all(default_tctx)

    assert isinstance(result, (list, tuple))
