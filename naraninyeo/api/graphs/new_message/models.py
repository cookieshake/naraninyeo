import operator
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict

from naraninyeo.api.infrastructure.interfaces import Clock, MemoryRepository, MessageRepository, PlanActionExecutor
from naraninyeo.core.models import (
    Bot,
    BotMessage,
    EvaluationFeedback,
    MemoryItem,
    Message,
    PlanActionResult,
    ResponsePlan,
    TenancyContext,
)


class NewMessageGraphState(BaseModel):
    current_tctx: TenancyContext
    current_bot: Bot
    memories: List[MemoryItem]
    status: Literal["processing", "completed", "failed"]
    incoming_message: Message
    latest_history: List[Message]
    response_plan: Optional[ResponsePlan] = None
    plan_action_results: Optional[List[PlanActionResult]] = None
    evaluation_count: int = 0
    latest_evaluation_feedback: Optional[EvaluationFeedback] = None
    draft_messages: Optional[List[BotMessage]] = None
    outgoing_messages: Optional[Annotated[List[BotMessage], operator.add]] = None


class NewMessageGraphContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    clock: Clock
    message_repository: MessageRepository
    memory_repository: MemoryRepository
    plan_action_executor: PlanActionExecutor
