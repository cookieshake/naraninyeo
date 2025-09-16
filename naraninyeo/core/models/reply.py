from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from naraninyeo.core.models.memory import MemoryItem
from naraninyeo.core.models.message import Message


@dataclass
class EnvironmentalContext:
    timestamp: datetime
    location: str


@dataclass
class KnowledgeReference:
    content: str
    source_name: str
    timestamp: Optional[datetime] = None


@dataclass
class ReplyContext:
    environment: EnvironmentalContext
    last_message: Message
    latest_history: list[Message]
    knowledge_references: list[KnowledgeReference]
    processing_logs: list[str]
    short_term_memory: list[MemoryItem] | None = None
