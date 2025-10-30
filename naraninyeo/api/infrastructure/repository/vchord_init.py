from asyncpg import Pool


class VchordInit:
    def __init__(self, pool: Pool):
        self.pool = pool

    CREATE_SCHEMA = """
        CREATE SCHEMA IF NOT EXISTS naraninyeo;
    """

    CREATE_TABLE_BOT = """
        CREATE TABLE IF NOT EXISTS naraninyeo.bots (
            tenant_id VARCHAR(255) NOT NULL,
            bot_id VARCHAR(255) PRIMARY KEY,
            bot_name VARCHAR(255) NOT NULL,
            author_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,

            PRIMARY KEY (tenant_id, bot_id)
        );
    """

    CREATE_TABLE_ATTACHMENT = """
        CREATE TABLE IF NOT EXISTS naraninyeo.attachments (
            tenant_id VARCHAR(255) NOT NULL,
            attachment_id VARCHAR(255) NOT NULL,
            attachment_type VARCHAR(255) NOT NULL,
            content_type VARCHAR(255),
            content_length BIGINT,
            url TEXT,

            PRIMARY KEY (tenant_id, attachment_id);
        );
    """

    CREATE_TABLE_MESSAGE = """
        CREATE TABLE IF NOT EXISTS naraninyeo.messages (
            tenant_id VARCHAR(255) NOT NULL,
            message_id VARCHAR(255) NOT NULL,
            channel_id VARCHAR(255) NOT NULL,
            channel_name VARCHAR(255) NOT NULL,
            author_id VARCHAR(255) NOT NULL,
            author_name VARCHAR(255) NOT NULL,
            content_text TEXT NOT NULL,
            attachment_ids VARCHAR(255)[],
            timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (tenant_id, message_id);
        )
    """

    async def run(self):
        async with self.pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLE_BOT)
            await conn.execute(self.CREATE_TABLE_ATTACHMENT)
            await conn.execute(self.CREATE_TABLE_MESSAGE)
