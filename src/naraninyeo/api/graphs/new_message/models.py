import operator
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from naraninyeo.api.agents.information_gatherer import InformationGathererOutput
from naraninyeo.api.infrastructure.adapter.naver_search import NaverSearchClient
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
    evaluation_count: int = 0
    information_gathering_results: List[InformationGathererOutput] = Field(default_factory=list)
    latest_evaluation_feedback: Optional[EvaluationFeedback] = None
    draft_messages: List[BotMessage] = Field(default_factory=list)
    outgoing_messages: Annotated[List[BotMessage], operator.add] = Field(default_factory=list)


class NewMessageGraphContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    clock: Clock
    message_repository: MessageRepository
    memory_repository: MemoryRepository
    plan_action_executor: PlanActionExecutor
    naver_search_client: NaverSearchClient
