import asyncio
import json
import logging
import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import nanoid
from aiobotocore.session import get_session
from aiokafka import AIOKafkaConsumer, ConsumerRecord
from anyio import TemporaryFile

from naraninyeo.core.models import Attachment, Author, Channel, Message, MessageContent
from naraninyeo.router.api_client import APIClient
from naraninyeo.router.phone_client import PhoneClient


class MessageRouter:
    def __init__(self) -> None:
        self.test_emoji = "🧑‍🔬"
        self.first_client = APIClient(os.environ["FIRST_API_URL"], os.environ["BOT_ID"])
        self.second_client = APIClient(os.environ["SECOND_API_URL"], os.environ["BOT_ID"])
        self.phone_client = PhoneClient(os.environ["PHONE_API_URL"])
        self.consumer = AIOKafkaConsumer(
            os.environ["KAFKA_TOPIC"],
            bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            group_id=os.environ["KAFKA_GROUP_ID"],
            auto_offset_reset="earliest",
            enable_auto_commit=False,
        )
        self.session = get_session()
        self.bucket = os.environ["S3_BUCKET"]
        self.aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
        self.aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"]
        self.s3_endpoint_url = os.environ["S3_ENDPOINT_URL"]

    async def run(self) -> None:
        await self.consumer.start()
        try:
            async for msg in self.consumer:
                await self.process_message(msg)
                await self.consumer.commit()
        finally:
            await self.consumer.stop()

    async def process_message(self, msg: ConsumerRecord) -> None:
        if msg.value is None:
            return
        try:
            message = await self.parse_message(json.loads(msg.value))
        except Exception as e:
            logging.error(e)
            return

        answer_required = message.content.text.startswith("/")
        client = self.get_client(shuffle=answer_required)
        try:
            async for bot_message in client.new_message(message, reply_needed=answer_required):
                if client == self.first_client:
                    prefix = ""
                else:
                    prefix = self.test_emoji + " "
                await self.phone_client.reply(
                    bot_message.channel.channel_id,
                    prefix + bot_message.content.text,
                )
                await asyncio.sleep(2)
        except Exception as e:
            logging.error(e)
            if answer_required:
                await self.phone_client.reply(
                    message.channel.channel_id,
                    f"읭? {e}",
                )

    async def parse_message(self, message_data: dict) -> Message:
        message_data["json"]["message"] = message_data["json"]["message"].replace(self.test_emoji, "")
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
                        await self.upload_attachment(
                            Attachment(
                                attachment_id=nanoid.generate(),
                                attachment_type="image",
                                url=attachment["url"],
                            )
                        )
                    ],
                )
            case "3":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=[
                        await self.upload_attachment(
                            Attachment(
                                attachment_id=nanoid.generate(),
                                attachment_type="video",
                                url=attachment["url"],
                            )
                        )
                    ],
                )
            case "18":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=[
                        await self.upload_attachment(
                            Attachment(
                                attachment_id=nanoid.generate(),
                                attachment_type="file",
                                url=attachment["url"],
                            )
                        )
                    ],
                )
            case "27":
                content = MessageContent(
                    text=message_data["json"]["message"],
                    attachments=await asyncio.gather(
                        *[
                            self.upload_attachment(
                                Attachment(
                                    attachment_id=nanoid.generate(),
                                    attachment_type="image",
                                    url=url,
                                )
                            )
                            for url in attachment["imageUrls"]
                        ]
                    ),
                )
            case _:
                content = MessageContent(text=message_data["json"]["message"], attachments=[])
        timestamp = datetime.fromtimestamp(int(message_data["json"]["created_at"]), tz=ZoneInfo("Asia/Seoul"))

        return Message(
            message_id=message_id,
            channel=channel,
            author=author,
            content=content,
            timestamp=timestamp,
        )

    async def upload_attachment(self, attachment: Attachment) -> Attachment:
        if attachment.url is None:
            return attachment

        key = f"{attachment.attachment_id[0]}/{attachment.attachment_id[1]}/{attachment.attachment_id[2:]}"

        async with TemporaryFile() as temp_file:
            async with httpx.AsyncClient() as client:
                async with client.stream("GET", attachment.url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        await temp_file.write(chunk)
            await temp_file.seek(0)
            async with self.session.create_client(
                "s3",
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                endpoint_url=self.s3_endpoint_url,
            ) as client:
                await client.upload_fileobj(
                    temp_file,
                    self.bucket,
                    key,
                )  # pyright: ignore
        return Attachment(
            attachment_id=attachment.attachment_id,
            attachment_type=attachment.attachment_type,
            url=f"s3://{self.bucket}/{key}",
        )

    def get_client(self, shuffle: bool = False):
        if shuffle:
            p = 6 / 7
            return self.first_client if random.random() < p else self.second_client
        return self.first_client
