from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel

class RetrievalPlan(BaseModel):
    query: str

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
