from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class MemoryItem(BaseModel):
    memory_id: str
    channel_id: str
    kind: Literal["ephemeral", "persona", "task"] = "ephemeral"
    content: str
    importance: int = 1
    created_at: datetime
    expires_at: Optional[datetime] = None
