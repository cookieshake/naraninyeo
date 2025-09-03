"""
Kafka 메시지 처리 진입점
얇은 인터페이스 계층 - 메시지를 받아서 서비스로 위임만 함
"""

import asyncio
import json
import logging
import signal
import traceback
import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from aiohttp import web
from aiokafka import AIOKafkaConsumer, ConsumerRecord

from naraninyeo.di import container
from naraninyeo.domain.model.message import Attachment, Author, Channel, Message, MessageContent
from naraninyeo.infrastructure.settings import Settings


class APIClient:
    def __init__(self, settings: Settings):
        self.api_url = settings.NARANINYEO_API_URL

    async def send_response(self, message: Message):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/reply",
                json={
                    "type": "text",
                    "room": message.channel.channel_id,
                    "data": message.content.text,
                },
            )
            response.raise_for_status()


class KafkaConsumer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.consumer = AIOKafkaConsumer(
            settings.KAFKA_TOPIC,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.KAFKA_GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        self.client = httpx.AsyncClient()
        self.api_client = APIClient(settings)

    async def start(self):
        await self.consumer.start()
        async for msg in self.consumer:
            await self.process_message(msg)
            await self.consumer.commit()

    async def stop(self):
        await self.consumer.stop()

    async def process_message(self, msg: ConsumerRecord[bytes, bytes]):
        try:
            # 1. 메시지 파싱
            if msg.value is None:
                return
            message_string = msg.value.decode("utf-8")

            value = json.loads(message_string)
            message = await self.parse_message(value)

            await self.client.post(
                f"{self.settings.NARANINYEO_NEW_MESSAGE_API}/handle_new_message",
                content=message.model_dump_json(),
                headers={"Content-Type": "application/json"},
                timeout=60.0
            )
            async with self.client.stream(
                "POST", f"{self.settings.NARANINYEO_NEW_MESSAGE_API}/handle_new_message",
                content=message.model_dump_json(),
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    logging.info(f"Response from API: {line}")
                    response = Message.model_validate_json(line)
                    await self.api_client.send_response(response)

        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON message: {e}")
        except Exception as e:
            logging.error(f"Error processing message: {e}, {traceback.format_exc()}")

    async def parse_message(self, message_data: dict) -> Message:
        message_id = message_data["json"]["id"]
        channel = Channel(
            channel_id=message_data["json"]["chat_id"],
            channel_name=message_data["room"] or "unknown",
        )
        author = Author(
            author_id=message_data["json"]["user_id"],
            author_name=message_data["sender"] or "unknown",
        )
        attachment = json.loads(message_data["json"]["attachment"])
        match message_data["json"]["type"]:
            case "2":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=[
                        await self.create_with_content_url(
                            attachment_id=str(uuid.uuid4()),
                            attachment_type="image",
                            content_url=attachment["url"],
                        )
                    ],
                )
            case "3":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=[
                        await self.create_with_content_url(
                            attachment_id=str(uuid.uuid4()),
                            attachment_type="video",
                            content_url=attachment["url"],
                        )
                    ],
                )
            case "18":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=[
                        await self.create_with_content_url(
                            attachment_id=str(uuid.uuid4()),
                            attachment_type="file",
                            content_url=attachment["url"],
                        )
                    ],
                )
            case "27":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=await asyncio.gather(
                        *[
                            self.create_with_content_url(
                                attachment_id=str(uuid.uuid4()),
                                attachment_type="image",
                                content_url=url,
                            )
                            for url in attachment["imageUrls"]
                        ]
                    ),
                )
            case _:
                content = MessageContent(text=message_data["json"]["message"], attachments=[])
        timestamp = datetime.fromtimestamp(int(message_data["json"]["created_at"]), tz=ZoneInfo(self.settings.TIMEZONE))

        return Message(
            message_id=message_id,
            channel=channel,
            author=author,
            content=content,
            timestamp=timestamp,
        )

    async def create_with_content_url(
        self,
        attachment_id: str,
        attachment_type: Literal["image", "video", "file"],
        content_url: str,
    ) -> Attachment:
        async with httpx.AsyncClient() as client:
            response = await client.get(content_url)
            return Attachment(
                attachment_id=attachment_id,
                attachment_type=attachment_type,
                content_type=response.headers.get("Content-Type"),
                content_length=response.headers.get("Content-Length"),
            )


async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text="OK", status=200)


async def start_health_server(port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Health check server started on port {port}")
    return runner


async def main():
    settings = await container.get(Settings)

    kafka_consumer = KafkaConsumer(settings=settings)

    # Start health check server with access to the Kafka consumer
    health_server = await start_health_server(settings.PORT)

    # Create a task for Kafka consumer
    kafka_task = asyncio.create_task(kafka_consumer.start())

    def handle_shutdown_signal(sig):
        logging.info(f"Received shutdown signal: {sig}")
        kafka_task.cancel()

    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown_signal, sig)

    try:
        # Wait for either the Kafka task to complete or a shutdown signal
        await kafka_task
    except asyncio.CancelledError:
        logging.info("Kafka consumer task was cancelled")
    except Exception as e:
        logging.error(f"Error occurred: {e}")
    finally:
        logging.info("Shutting down application...")
        await kafka_consumer.stop()
        await health_server.cleanup()
        logging.info("Application shutdown complete")
