from datetime import datetime
from enum import Enum
from typing import List, Optional, Literal, Union

from pydantic import BaseModel, computed_field

from naraninyeo.domain.model.message import Message

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

class UrlRef(BaseModel):
    kind: Literal["url"] = "url"
    value: str

    @computed_field
    def as_text(self) -> str:
        return self.value

class ChatHistoryRef(BaseModel):
    kind: Literal["chat_history"] = "chat_history"
    value: List[Message]

    @computed_field
    def as_text(self) ->str:
        return "\n".join(message.text_repr for message in self.value)


Ref = Union[UrlRef, ChatHistoryRef]

class RetrievalResult(BaseModel):
    plan: RetrievalPlan
    result_id: str
    ref: Ref
    status: RetrievalStatus
    status_reason: RetrievalStatusReason
    content: str
    source_name: str
    source_timestamp: Optional[datetime]
