from datetime import datetime
from typing import Sequence

from asyncpg import Pool

from naraninyeo.core.models import MemoryItem, TenancyContext


class VchordMemoryRepository:
    def __init__(self, pool: Pool):
        self.pool = pool

    async def upsert_many(self, tctx: TenancyContext, memory_items: Sequence[MemoryItem]) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for item in memory_items:
                    await conn.execute(
                        """
                        INSERT INTO memory_items (
                            tenant_id, memory_id, bot_id, channel_id, kind,
                            content, created_at, updated_at, expires_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (tenant_id, memory_id) DO UPDATE SET
                            bot_id = EXCLUDED.bot_id,
                            channel_id = EXCLUDED.channel_id,
                            kind = EXCLUDED.kind,
                            content = EXCLUDED.content,
                            updated_at = EXCLUDED.updated_at,
                            expires_at = EXCLUDED.expires_at
                        """,
                        tctx.tenant_id,
                        item.memory_id,
                        item.bot_id,
                        item.channel_id,
                        item.kind,
                        item.content,
                        item.created_at,
                        item.updated_at,
                        item.expires_at,
                    )

    async def delete_many(self, tctx: TenancyContext, memory_item_ids: Sequence[str]) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM memory_items
                WHERE tenant_id = $1 AND memory_id = ANY($2)
                """,
                tctx.tenant_id,
                memory_item_ids,
            )
            # Result is in the format "DELETE <number_of_rows>"
            return int(result.split(" ")[1])

    async def delete_expired(self, tctx: TenancyContext, current_time: datetime) -> int:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM memory_items
                WHERE tenant_id = $1 AND expires_at < $2
                """,
                tctx.tenant_id,
                current_time,
            )
            # Result is in the format "DELETE <number_of_rows>"
            return int(result.split(" ")[1])

    async def get_channel_memory_items(
        self, tctx: TenancyContext, bot_id: str, channel_id: str, limit: int = 100
    ) -> Sequence[MemoryItem]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT memory_id, bot_id, channel_id, kind,
                       content, created_at, updated_at, expires_at
                FROM memory_items
                WHERE tenant_id = $1 AND bot_id = $2 AND channel_id = $3
                ORDER BY created_at DESC
                LIMIT $4
                """,
                tctx.tenant_id,
                bot_id,
                channel_id,
                limit,
            )
            return [
                MemoryItem(
                    memory_id=row["memory_id"],
                    bot_id=row["bot_id"],
                    channel_id=row["channel_id"],
                    kind=row["kind"],
                    content=row["content"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    expires_at=row["expires_at"],
                )
                for row in rows
            ]
