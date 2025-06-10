from pydantic import BaseModel
from typing import Optional

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

class MessageResponse(BaseModel):
    do_reply: bool
    message: str 