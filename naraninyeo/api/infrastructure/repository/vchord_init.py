from asyncpg import Pool
import httpx


class VchordInit:
    def __init__(self, pool: Pool):
        self.pool = pool

    DATABASE_INIT = """
        CREATE SCHEMA IF NOT EXISTS naraninyeo;
        CREATE EXTENSION IF NOT EXISTS vchord CASCADE;
        CREATE EXTENSION IF NOT EXISTS pg_tokenizer CASCADE;
        CREATE EXTENSION IF NOT EXISTS vchord_bm25 CASCADE;
    """

    MODEL_INIT = """
        SELECT create_huggingface_model('solar_pro_tokenizer', $1);
    """

    TOKENIZER_INIT = """
        SELECT create_tokenizer('solar_pro_tokenizer', $$
            model = "solar_pro_tokenizer"
        $$);
    """

    CREATE_TABLE_BOT = """
        CREATE TABLE IF NOT EXISTS naraninyeo.bots (
            tenant_id VARCHAR(255) NOT NULL,
            bot_id VARCHAR(255) NOT NULL,
            bot_name VARCHAR(255) NOT NULL,
            author_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,

            PRIMARY KEY (tenant_id, bot_id)
        );
    """

    CREATE_TABLE_ATTACHMENT = """
        CREATE TABLE IF NOT EXISTS naraninyeo.attachments (
            tenant_id VARCHAR(255) NOT NULL,
            message_id VARCHAR(255) NOT NULL,
            attachment_id VARCHAR(255) NOT NULL,
            attachment_type VARCHAR(255) NOT NULL,
            content_type VARCHAR(255),
            content_length BIGINT,
            url TEXT,

            PRIMARY KEY (tenant_id, message_id, attachment_id)
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
            content_text_gvec vector(768),
            content_text_bvec bm25vector,
            attachment_ids VARCHAR(255)[],
            timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (tenant_id, message_id)
        );
        CREATE INDEX IF NOT EXISTS naraninyeo_messages_content_text_bvec_bm25_idx
        ON naraninyeo.messages
        USING bm25 (content_text_bvec bm25_ops);
    """

    CREATE_TABLE_MEMORY_ITEM = """
        CREATE TABLE IF NOT EXISTS naraninyeo.memory_items (
            tenant_id VARCHAR(255) NOT NULL,
            memory_id VARCHAR(255) NOT NULL,
            bot_id VARCHAR(255) NOT NULL,
            channel_id VARCHAR(255) NOT NULL,
            kind VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE,

            PRIMARY KEY (tenant_id, memory_id)
        );
    """

    async def run(self):
        async with httpx.AsyncClient() as client:
            response = await client.get("https://huggingface.co/upstage/solar-pro-tokenizer/raw/main/tokenizer.json")
            tokenizer = response.text
        async with self.pool.acquire() as conn:
            await conn.execute(self.DATABASE_INIT)
            await conn.execute(self.MODEL_INIT, tokenizer)
            await conn.execute(self.TOKENIZER_INIT)
            await conn.execute(self.CREATE_TABLE_BOT)
            await conn.execute(self.CREATE_TABLE_ATTACHMENT)
            await conn.execute(self.CREATE_TABLE_MESSAGE)
            await conn.execute(self.CREATE_TABLE_MEMORY_ITEM)
