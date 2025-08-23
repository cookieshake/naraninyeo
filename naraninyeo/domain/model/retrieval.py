from datetime import datetime
from enum import Enum
from typing import Optional, Literal

from pydantic import BaseModel

class RetrievalPlan(BaseModel):
    """A retrieval plan specifying how to search and with what query."""
    query: str
    search_type: Literal[
        "naver_web",
        "naver_news",
        "naver_blog",
        "naver_doc",
        "chat_history",
    ]

class RetrievalStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"

class RetrievalStatusReason(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"

class RetrievalResult(BaseModel):
    status: RetrievalStatus
    status_reason: RetrievalStatusReason
    content: str
    source_name: str
    source_timestamp: Optional[datetime]
    ref: str
