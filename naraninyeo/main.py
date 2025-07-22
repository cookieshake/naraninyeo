import asyncio
from datetime import datetime
import uuid
from zoneinfo import ZoneInfo

import httpx
from naraninyeo.core.config import settings
from naraninyeo.core.database import mc
from naraninyeo.models.message import Attachment, Author, Channel, Message, MessageContent
from naraninyeo.services.message import handle_message
import json
import loguru

import anyio
from aiokafka import AIOKafkaConsumer

async def parse_message(message_data: dict) -> Message:
    message_id = message_data["json"]["id"]
    channel = Channel(
        channel_id=message_data["json"]["chat_id"],
        channel_name=message_data["room"] or "unknown"
    )
    author = Author(
        author_id=message_data["json"]["user_id"],
        author_name=message_data["json"]["sender"] or "unknown"
    )
    attachment = json.loads(message_data["json"]["attachment"])
    match message_data["json"]["type"]:
        case "2":
            content = MessageContent(
                text=message_data["json"]["message"],
                attachments=[
                    await Attachment.create_with_content_url(
                        attachment_id=str(uuid.uuid4()),
                        attachment_type="image",
                        content_url=attachment["url"]
                    )
                ]
            )
        case "3":
            content = MessageContent(
                text=message_data["json"]["message"],
                attachments=[
                    await Attachment.create_with_content_url(
                        attachment_id=str(uuid.uuid4()),
                        attachment_type="video",
                        content_url=attachment["url"]
                    )
                ]
            )
        case "18":
            content = MessageContent(
                text=message_data["json"]["message"],
                attachments=[
                    await Attachment.create_with_content_url(
                        attachment_id=str(uuid.uuid4()),
                        attachment_type="file",
                        content_url=attachment["url"]
                    )
                ]
            )
        case "27":
            content = MessageContent(
                text=message_data["json"]["message"],
                attachments=await asyncio.gather(*[
                    Attachment.create_with_content_url(
                        attachment_id=str(uuid.uuid4()),
                        attachment_type="image",
                        content_url=url
                    )
                    for url in attachment["imageUrls"]
                ])
            )
        case _:
            content = MessageContent(
                text=message_data["json"]["message"]
            )
    timestamp = datetime.fromtimestamp(int(message_data["json"]["created_at"]), tz=ZoneInfo("Asia/Seoul"))
    return Message(
        message_id=message_id,
        channel=channel,
        author=author,
        content=content,
        timestamp=timestamp
    )

async def send_response(response: Message):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.NARANINYEO_API_URL}/reply",
            json={
                "type": "text",
                "room": response.channel.channel_id,
                "data": response.content.text
            }
        )
        response.raise_for_status()

async def main():
    await mc.connect_to_database()
    consumer = AIOKafkaConsumer(
        settings.KAFKA_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.KAFKA_GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=False
    )
    loguru.logger.info(f"Starting consumer for topic: {settings.KAFKA_TOPIC}")
    await consumer.start()
    try:
        async for msg in consumer:
            try:
                value = json.loads(msg.value.decode("utf-8"))
                loguru.logger.info(f"Received message: {value}")
                message = await parse_message(value)
                async for r in handle_message(message):
                    loguru.logger.info(f"Sending response: {r.content.text}")
                    await send_response(r)
                await consumer.commit()
            except Exception as e:
                loguru.logger.error(f"Error processing message: {e}")
    finally:
        loguru.logger.info("Stopping consumer")
        await consumer.stop()
        loguru.logger.info("Consumer stopped")
        loguru.logger.info("Closing database connection")
        await mc.close_database_connection()

if __name__ == "__main__":
    anyio.run(main)