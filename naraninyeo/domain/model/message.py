from zoneinfo import ZoneInfo
from typing import Literal, Optional
from datetime import datetime

from pydantic import BaseModel

class Author(BaseModel):
    author_id: str
    author_name: str

class Attachment(BaseModel):
    attachment_id: str
    attachment_type: Literal["image", "video", "file"]
    content_type: Optional[str] = None
    content_length: Optional[int] = None

class MessageContent(BaseModel):
    text: str
    attachments: list[Attachment]

class Channel(BaseModel):
    channel_id: str
    channel_name: str

class Message(BaseModel):
    message_id: str
    channel: Channel
    author: Author
    content: MessageContent
    timestamp: datetime

    @property
    def text_repr(self) -> str:
        return f"{self.timestamp.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")} {self.author.author_name} : {self.content.text[:200]}"
