

from typing import Sequence

from asyncpg import Pool

from naraninyeo.api.infrastructure.interfaces import TextEmbedder
from naraninyeo.core.models import Attachment, Author, Channel, Message, MessageContent, TenancyContext

# CREATE_TABLE_MESSAGE = """
#     CREATE TABLE IF NOT EXISTS naraninyeo.messages (
#         tenant_id VARCHAR(255) NOT NULL,
#         message_id VARCHAR(255) NOT NULL,
#         channel_id VARCHAR(255) NOT NULL,
#         channel_name VARCHAR(255) NOT NULL,
#         author_id VARCHAR(255) NOT NULL,
#         author_name VARCHAR(255) NOT NULL,
#         content_text TEXT NOT NULL,
#         content_text_embeddings embedding vector(768),
#         timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
#
#         PRIMARY KEY (tenant_id, message_id);
#     )
# """

# CREATE_TABLE_ATTACHMENT = """
#     CREATE TABLE IF NOT EXISTS naraninyeo.attachments (
#         tenant_id VARCHAR(255) NOT NULL,
#         message_id VARCHAR(255) NOT NULL,
#         attachment_id VARCHAR(255) NOT NULL,
#
#         attachment_type VARCHAR(255) NOT NULL,
#         content_type VARCHAR(255),
#         content_length BIGINT,
#         url TEXT,
#
#         PRIMARY KEY (tenant_id, message_id, attachment_id);
#     );
# """

class VchordMessageRepository:
    def __init__(self, pool: Pool, text_embedder: TextEmbedder):
        self.pool = pool
        self.text_embedder = text_embedder

    async def upsert(self, tctx: TenancyContext, message: Message) -> None:
        content_text_embeddings = await self.text_embedder.embed_docs([message.content.text])
        content_text_embeddings = content_text_embeddings[0]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO naraninyeo.messages (
                        tenant_id, message_id, channel_id, channel_name,
                        author_id, author_name, content_text, content_text_embeddings, timestamp
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (tenant_id, message_id) DO UPDATE SET
                        channel_id = EXCLUDED.channel_id,
                        channel_name = EXCLUDED.channel_name,
                        author_id = EXCLUDED.author_id,
                        author_name = EXCLUDED.author_name,
                        content_text = EXCLUDED.content_text,
                        content_text_embeddings = EXCLUDED.content_text_embeddings,
                        timestamp = EXCLUDED.timestamp
                    """,
                    tctx.tenant_id,
                    message.message_id,
                    message.channel.channel_id,
                    message.channel.channel_name,
                    message.author.author_id,
                    message.author.author_name,
                    message.content.text,
                    content_text_embeddings,
                    message.timestamp
                )

                if message.content.attachments:
                    await conn.executemany(
                        """
                        INSERT INTO naraninyeo.attachments (
                            tenant_id, message_id, attachment_id, attachment_type,
                            content_type, content_length, url
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (tenant_id, message_id, attachment_id) DO UPDATE SET
                            attachment_type = EXCLUDED.attachment_type,
                            content_type = EXCLUDED.content_type,
                            content_length = EXCLUDED.content_length,
                            url = EXCLUDED.url
                        """,
                        [
                            (
                                tctx.tenant_id,
                                message.message_id,
                                a.attachment_id,
                                a.attachment_type,
                                a.content_type,
                                a.content_length,
                                a.url
                            )
                            for a in message.content.attachments
                        ]
                    )

    async def _parse_message_row(self, row) -> Message:
        attachments = []
        if row["attachment_ids_result"]:
            for i in range(len(row["attachment_ids_result"])):
                attachments.append(Attachment(
                    attachment_id=row["attachment_ids_result"][i],
                    attachment_type=row["attachment_types"][i],
                    content_type=row["content_types"][i],
                    content_length=row["content_lengths"][i],
                    url=row["urls"][i]
                ))

        message = Message(
            message_id=row["message_id"],
            channel=Channel(
                channel_id=row["channel_id"],
                channel_name=row["channel_name"]
            ),
            author=Author(
                author_id=row["author_id"],
                author_name=row["author_name"]
            ),
            content=MessageContent(
                text=row["content_text"],
                attachments=attachments
            ),
            timestamp=row["timestamp"]
        )
        return message

    async def _get_channel_messages(
        self,
        tctx: TenancyContext,
        channel_id: str,
        reference_message_id: str,
        limit: int,
        before: bool
    ) -> Sequence[Message]:
        operator = "<" if before else ">"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT m.message_id, m.channel_id, m.channel_name,
                       m.author_id, m.author_name, m.content_text,
                       m.timestamp,
                       ARRAY_AGG(a.attachment_id) FILTER (WHERE a.attachment_id IS NOT NULL) AS attachment_ids_result,
                       ARRAY_AGG(a.attachment_type) FILTER (WHERE a.attachment_id IS NOT NULL) AS attachment_types,
                       ARRAY_AGG(a.content_type) FILTER (WHERE a.attachment_id IS NOT NULL) AS content_types,
                       ARRAY_AGG(a.content_length) FILTER (WHERE a.attachment_id IS NOT NULL) AS content_lengths,
                       ARRAY_AGG(a.url) FILTER (WHERE a.attachment_id IS NOT NULL) AS urls
                FROM naraninyeo.messages m
                LEFT JOIN naraninyeo.attachments a
                    ON a.tenant_id = m.tenant_id AND a.message_id = m.message_id
                WHERE m.tenant_id = $1 AND m.channel_id = $2
                  AND m.timestamp {operator} (
                    SELECT timestamp FROM naraninyeo.messages
                    WHERE tenant_id = $1 AND message_id = $3
                  )
                GROUP BY m.tenant_id, m.message_id, m.channel_id, m.channel_name,
                         m.author_id, m.author_name, m.content_text, m.timestamp
                ORDER BY m.timestamp ASC
                LIMIT $4
                """,
                tctx.tenant_id,
                channel_id,
                reference_message_id,
                limit
            )

            messages = []
            for row in rows:
                message = await self._parse_message_row(row)
                messages.append(message)
            return messages

    async def get_channel_messages_before(
        self,
        tctx: TenancyContext,
        channel_id: str,
        before_message_id: str,
        limit: int = 10
    ) -> Sequence[Message]:
        return await self._get_channel_messages(tctx, channel_id, before_message_id, limit, before=True)

    async def get_channel_messages_after(
        self,
        tctx: TenancyContext,
        channel_id: str,
        after_message_id: str,
        limit: int = 10
    ) -> Sequence[Message]:
        return await self._get_channel_messages(tctx, channel_id, after_message_id, limit, before=False)

    async def text_search_messages(
        self,
        tctx: TenancyContext,
        channel_id: str,
        query: str,
        limit: int = 10
    ) -> Sequence[Message]:
        query_embedding = await self.text_embedder.embed_queries([query])
        query_embedding = query_embedding[0]
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.message_id, m.channel_id, m.channel_name,
                       m.author_id, m.author_name, m.content_text,
                       m.timestamp,
                       m.content_text_embeddings <-> $3 AS similarity,
                       ARRAY_AGG(a.attachment_id) FILTER (WHERE a.attachment_id IS NOT NULL) AS attachment_ids_result,
                       ARRAY_AGG(a.attachment_type) FILTER (WHERE a.attachment_id IS NOT NULL) AS attachment_types,
                       ARRAY_AGG(a.content_type) FILTER (WHERE a.attachment_id IS NOT NULL) AS content_types,
                       ARRAY_AGG(a.content_length) FILTER (WHERE a.attachment_id IS NOT NULL) AS content_lengths,
                       ARRAY_AGG(a.url) FILTER (WHERE a.attachment_id IS NOT NULL) AS urls
                FROM naraninyeo.messages m
                LEFT JOIN naraninyeo.attachments a
                    ON a.tenant_id = m.tenant_id AND a.message_id = m.message_id
                WHERE m.tenant_id = $1 AND m.channel_id = $2
                ORDER BY similarity DESC
                LIMIT $4
                """,
                tctx.tenant_id,
                channel_id,
                query_embedding,
                limit
            )

            messages = []
            for row in rows:
                message = await self._parse_message_row(row)
                messages.append(message)
            return messages
