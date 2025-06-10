from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Author(BaseModel):
    name: str
    hash: Optional[str] = None
    avatar: Optional[str] = None

class MessageRequest(BaseModel):
    room: str
    channelId: str
    author: Author
    content: str
    isGroupChat: bool
    packageName: str
    isDebugRoom: bool
    image: Optional[str] = None
    isMention: bool
    logId: str
    isMultiChat: bool

class MessageDocument(BaseModel):
    message_id: str = Field(alias="_id")
    room: str
    channel_id: str
    author_name: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    has_response: bool = False
    response_content: Optional[str] = None

class MessageResponse(BaseModel):
    do_reply: bool
    message: str 