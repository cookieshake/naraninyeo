from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

from naraninyeo.domain.model.message import Message

class EnvironmentalContext(BaseModel):
    timestamp: datetime
    location: str

class KnowledgeReference(BaseModel):
    content: str
    source_name: str
    timestamp: Optional[datetime]

class ReplyContext(BaseModel):
    environment: EnvironmentalContext
    last_message: Message
    latest_history: List[Message]
    knowledge_references: List[KnowledgeReference]
    processing_logs: list[str]

    
