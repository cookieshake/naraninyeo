from datetime import datetime
from typing import Sequence

from asyncpg import Pool

from naraninyeo.core.interfaces import TextEmbedder
from naraninyeo.core.models import MemoryItem, TenancyContext


class VchordMemoryRepository:
    def __init__(self, pool: Pool, text_embedder: TextEmbedder):
        self.pool = pool
        self.text_embedder = text_embedder

    @staticmethod
    def _format_pgvector(values: Sequence[float]) -> str:
        return "[" + ",".join(str(component) for component in values) + "]"

    async def upsert_many(self, tctx: TenancyContext, memory_items: Sequence[MemoryItem]) -> None:
        if not memory_items:
            return
        contents = [item.content for item in memory_items]
        embeddings = await self.text_embedder.embed_docs(contents)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for item, embedding in zip(memory_items, embeddings):
                    await conn.execute(
                        """
                        INSERT INTO memory_items (
                            tenant_id, memory_id, bot_id, channel_id, kind,
                            content, content_embedding, created_at, updated_at, expires_at
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (tenant_id, memory_id) DO UPDATE SET
                            bot_id = EXCLUDED.bot_id,
                            channel_id = EXCLUDED.channel_id,
                            kind = EXCLUDED.kind,
                            content = EXCLUDED.content,
                            content_embedding = EXCLUDED.content_embedding,
                            updated_at = EXCLUDED.updated_at,
                            expires_at = EXCLUDED.expires_at
                        """,
                        tctx.tenant_id,
                        item.memory_id,
                        item.bot_id,
                        item.channel_id,
                        item.kind,
                        item.content,
                        self._format_pgvector(embedding),
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
                ORDER BY updated_at DESC
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

    async def search_memories(
        self, tctx: TenancyContext, bot_id: str, channel_id: str, query_embedding: list[float], limit: int = 20
    ) -> Sequence[MemoryItem]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT memory_id, bot_id, channel_id, kind,
                       content, created_at, updated_at, expires_at
                FROM memory_items
                WHERE tenant_id = $1 AND bot_id = $2 AND channel_id = $3
                  AND content_embedding IS NOT NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY
                    content_embedding <-> $4
                    + EXTRACT(EPOCH FROM (NOW() - updated_at)) / 86400.0 * 0.01
                LIMIT $5
                """,
                tctx.tenant_id,
                bot_id,
                channel_id,
                self._format_pgvector(query_embedding),
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

    async def get_latest_memory_update_ts(self, tctx: TenancyContext, bot_id: str, channel_id: str) -> datetime | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT MAX(updated_at) AS latest_update
                FROM memory_items
                WHERE tenant_id = $1 AND bot_id = $2 AND channel_id = $3
                """,
                tctx.tenant_id,
                bot_id,
                channel_id,
            )
            return row["latest_update"] if row and row["latest_update"] else None
