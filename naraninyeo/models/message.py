from zoneinfo import ZoneInfo
import httpx
from pydantic import BaseModel, Field, computed_field
from typing import Literal, Optional
from datetime import datetime

from naraninyeo.core.database import mc

class Author(BaseModel):
    author_id: str
    author_name: str

class Attachment(BaseModel):
    attachment_id: str
    attachment_type: Literal["image", "video", "file"]
    content_type: Optional[str] = None
    content_length: Optional[int] = None

    @classmethod
    async def create_with_content_url(
        cls,
        attachment_id: str,
        attachment_type: Literal["image", "video", "file"],
        content_url: str
    ) -> "Attachment":
        async with httpx.AsyncClient() as client:
            response = await client.get(content_url)
            attachment = cls(
                attachment_id=attachment_id,
                attachment_type=attachment_type,
                content_type=response.headers.get("Content-Type"),
                content_length=response.headers.get("Content-Length")
            )
            await attachment.save_content(response.content)
            return attachment

    async def save_content(self, content: bytes):
        await mc.db["attachment_content"].update_one(
            {"attachment_id": self.attachment_id},
            {"$set": {"content": content}},
            upsert=True
        )

    async def get_content(self) -> bytes:
        return await mc.db["attachment_content"].find_one({"attachment_id": self.attachment_id})["content"]

class MessageContent(BaseModel):
    text: str
    attachments: list[Attachment] = Field(default_factory=list)

class Channel(BaseModel):
    channel_id: str
    channel_name: str

class Message(BaseModel):
    message_id: str
    channel: Channel
    author: Author
    content: MessageContent
    timestamp: datetime

    async def save(self):
        await mc.db["messages"].update_one(
            {"message_id": self.message_id},
            {"$set": self.model_dump(by_alias=True)},
            upsert=True
        )

    @property
    def text_repr(self) -> str:
        return f"{self.timestamp.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")} {self.author.author_name} : {self.content.text[:200]}"