from typing import Sequence

from asyncpg import Pool

from naraninyeo.core.models import Bot, TenancyContext


class VchordBotRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def get(self, tctx: TenancyContext, bot_id: str) -> Bot | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT bot_id, bot_name, author_id, created_at
                FROM naraninyeo.bots
                WHERE tenant_id = $1 AND bot_id = $2
                """,
                tctx.tenant_id,
                bot_id,
            )
            if row:
                return Bot(
                    bot_id=row["bot_id"],
                    bot_name=row["bot_name"],
                    author_id=row["author_id"],
                    created_at=row["created_at"],
                )
            return None

    async def list_all(self, tctx: TenancyContext) -> Sequence[Bot]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT bot_id, bot_name, author_id, created_at
                FROM naraninyeo.bots
                WHERE tenant_id = $1
                """,
                tctx.tenant_id,
            )
            return [
                Bot(
                    bot_id=row["bot_id"],
                    bot_name=row["bot_name"],
                    author_id=row["author_id"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    async def create(self, tctx: TenancyContext, bot: Bot) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO naraninyeo.bots (tenant_id, bot_id, bot_name, author_id, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                tctx.tenant_id,
                bot.bot_id,
                bot.bot_name,
                bot.author_id,
                bot.created_at,
            )
