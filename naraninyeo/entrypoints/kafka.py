"""
Kafka 메시지 처리 진입점
얇은 인터페이스 계층 - 메시지를 받아서 서비스로 위임만 함
"""
import asyncio
from datetime import datetime
from typing import Literal
import uuid
from zoneinfo import ZoneInfo
import httpx
from opentelemetry import trace
import json
import logfire
import traceback
from aiokafka import AIOKafkaConsumer, ConsumerRecord

from naraninyeo.domain.application.new_message_handler import NewMessageHandler
from naraninyeo.domain.model.message import Attachment, Author, Channel, Message, MessageContent
from naraninyeo.infrastructure.settings import Settings
from naraninyeo.di import container


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
                    "data": message.content.text
                }
            )
            response.raise_for_status()

class KafkaConsumer:
    def __init__(
        self,
        settings: Settings,
        message_handler: NewMessageHandler,
        api_client: APIClient
    ):
        self.settings = settings
        self.message_handler = message_handler
        self.api_client = api_client
        self.consumer = AIOKafkaConsumer(
            settings.KAFKA_TOPIC,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.KAFKA_GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=False
        )

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
            
            async for response in self.message_handler.handle(message):
                await self.api_client.send_response(response)

        except json.JSONDecodeError as e:
            logfire.error(f"Invalid JSON message: {e}")
        except Exception as e:
            logfire.error("Error processing message: {error}, {traceback}", error=e, traceback=traceback.format_exc())

    async def parse_message(self, message_data: dict) -> Message:
        message_id = message_data["json"]["id"]
        channel = Channel(
            channel_id=message_data["json"]["chat_id"],
            channel_name=message_data["room"] or "unknown"
        )
        author = Author(
            author_id=message_data["json"]["user_id"],
            author_name=message_data["sender"] or "unknown"
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
                            content_url=attachment["url"]
                        )
                    ]
                )
            case "3":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=[
                        await self.create_with_content_url(
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
                        await self.create_with_content_url(
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
                        self.create_with_content_url(
                            attachment_id=str(uuid.uuid4()),
                            attachment_type="image",
                            content_url=url
                        )
                        for url in attachment["imageUrls"]
                    ])
                )
            case _:
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=[]
                )
        timestamp = datetime.fromtimestamp(
            int(message_data["json"]["created_at"]),
            tz=ZoneInfo(self.settings.TIMEZONE)
        )

        return Message(
            message_id=message_id,
            channel=channel,
            author=author,
            content=content,
            timestamp=timestamp
        )

    async def create_with_content_url(
        self,
        attachment_id: str,
        attachment_type: Literal["image", "video", "file"],
        content_url: str
    ) -> Attachment:
        async with httpx.AsyncClient() as client:
            response = await client.get(content_url)
            return Attachment(
                attachment_id=attachment_id,
                attachment_type=attachment_type,
                content_type=response.headers.get("Content-Type"),
                content_length=response.headers.get("Content-Length")
            )

async def main():
    settings = await container.get(Settings)
    api_client = APIClient(settings)
    message_handler = await container.get(NewMessageHandler)

    kafka_consumer = KafkaConsumer(
        settings=settings,
        message_handler=message_handler,
        api_client=api_client
    )
    try:
        await kafka_consumer.start()
    except Exception as e:
        logfire.error(f"Error occurred: {e}")
    finally:
        await kafka_consumer.stop()
