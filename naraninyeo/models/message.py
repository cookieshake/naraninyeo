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

class MessageDocument(MessageRequest):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class MessageResponse(BaseModel):
    do_reply: bool
    message: str 