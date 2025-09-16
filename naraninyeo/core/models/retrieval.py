from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from naraninyeo.core.models.message import Message


class RetrievalPlan(BaseModel):
    search_type: str
    query: str


@dataclass
class ChatHistoryRef:
    value: list[Message]

    @property
    def as_text(self) -> str:
        return "\n".join([m.text_repr for m in self.value])


@dataclass
class UrlRef:
    value: str

    @property
    def as_text(self) -> str:
        return self.value


class RetrievalStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RetrievalStatusReason(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class RetrievalResult:
    plan: RetrievalPlan
    result_id: str
    content: str
    ref: ChatHistoryRef | UrlRef
    status: RetrievalStatus
    status_reason: RetrievalStatusReason
    source_name: str
    source_timestamp: Optional[datetime]
