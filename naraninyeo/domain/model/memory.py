from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    memory_id: str
    channel_id: str
    kind: Literal["ephemeral", "persona", "task"] = "ephemeral"
    content: str
    importance: int = Field(default=1, ge=1, le=5)
    created_at: datetime
    expires_at: Optional[datetime] = None
    # Optional vector for future similarity lookup
    vector: Optional[list[float]] = None
