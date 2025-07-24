import asyncio
from datetime import datetime
import uuid
from zoneinfo import ZoneInfo
import json

from openinference import trace

from naraninyeo.models.message import Message, MessageContent, Author, Channel, Attachment

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("parse_message")
async def parse_message(message_data: dict) -> Message:
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