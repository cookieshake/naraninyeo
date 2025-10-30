

from dataclasses import dataclass
from typing import List, Literal, Optional, TypedDict
from pydantic import BaseModel, ConfigDict

from naraninyeo.api.infrastructure.interfaces import Clock, IdGenerator, MemoryRepository, MemoryRepository
from naraninyeo.core.models import Bot, Message, TenancyContext


class ManageMemoryGraphState(BaseModel):
    current_tctx: TenancyContext
    current_bot: Bot
    status: Literal["processing", "completed", "failed"]
    incoming_message: Message
    latest_history: Optional[List[Message]] = None

class ManageMemoryGraphContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    clock: Clock
    id_generator: IdGenerator
    memory_repository: MemoryRepository
