import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from naraninyeo.app.context import ReplyContextBuilder
from naraninyeo.app.pipeline import (
    DEFAULT_STEPS,
    ChatPipeline,
    PipelineTools,
    StepRegistry,
    default_step_order,
)
from naraninyeo.app.reply import NewMessageHandler, ReplyGenerator
from naraninyeo.assistant.memory_management import ConversationMemoryExtractor, MemoryStore
from naraninyeo.assistant.message_repository import MessageRepository
from naraninyeo.assistant.models import (
    Author,
    Channel,
    MemoryItem,
    Message,
    MessageContent,
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
    RetrievalStatusReason,
    UrlRef,
)
from naraninyeo.assistant.retrieval import (
    RetrievalExecutor,
    RetrievalPlanLog,
    RetrievalPlanner,
    RetrievalPostProcessor,
    RetrievalResultCollectorFactory,
)
from naraninyeo.settings import Settings


class InMemoryMessageRepository(MessageRepository):
    def __init__(self) -> None:
        self.saved: list[Message] = []

    async def save(self, message: Message) -> None:
        self.saved.append(message)

    async def get_surrounding_messages(
        self,
        message: Message,
        before: int,
        after: int,
    ) -> list[Message]:
        history = self.saved[-before:] + [message]
        history.sort(key=lambda item: item.timestamp)
        return history

    async def search_similar_messages(self, channel_id: str, keyword: str, limit: int) -> list[Message]:
        matches = [msg for msg in self.saved if msg.channel.channel_id == channel_id]
        return matches[-limit:]


class InMemoryMemoryStore(MemoryStore):
    def __init__(self, seed: list[MemoryItem] | None = None) -> None:
        self._items = list(seed or [])

    async def put(self, items: list[MemoryItem]) -> None:
        self._items.extend(items)

    async def recall(self, *, channel_id: str, limit: int, now: datetime) -> list[MemoryItem]:
        active = [
            item
            for item in self._items
            if item.channel_id == channel_id and (item.expires_at is None or item.expires_at > now)
        ]
        return active[:limit]


class QuietMemoryExtractor:
    async def extract_from_message(self, message: Message, history: list[Message]) -> list[MemoryItem]:
        return []


class FixedRetrievalPlanner:
    async def plan(self, context) -> list[RetrievalPlan]:
        return [RetrievalPlan(search_type="fake", query="테스트 검색어")]


class FakeCollector:
    def __init__(self) -> None:
        self._items: list[RetrievalResult] = []

    async def add(self, item: RetrievalResult) -> None:
        self._items.append(item)

    async def snapshot(self) -> list[RetrievalResult]:
        return list(self._items)


class FakeCollectorFactory:
    def create(self) -> FakeCollector:
        return FakeCollector()


class FakeRetrievalExecutor:
    async def execute_with_timeout(
        self,
        plans: list[RetrievalPlan],
        context,
        timeout_seconds: float,
        collector: FakeCollector,
    ) -> list[RetrievalPlanLog]:
        logs: list[RetrievalPlanLog] = []
        for plan in plans:
            result = RetrievalResult(
                plan=plan,
                result_id=f"fake-{plan.query}",
                content="테스트 지식",
                ref=UrlRef(value="https://example.com"),
                status=RetrievalStatus.SUCCESS,
                status_reason=RetrievalStatusReason.SUCCESS,
                source_name="example.com",
                source_timestamp=context.environment.timestamp,
            )
            await collector.add(result)
            logs.append(RetrievalPlanLog(plan=plan, matched=True))
        return logs


class FakeRetrievalPostProcessor:
    def process(self, results: list[RetrievalResult], context) -> list[RetrievalResult]:
        return results


class StaticReplyGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def stream(self, context) -> AsyncIterator[Message]:
        now = datetime.now(tz=context.last_message.timestamp.tzinfo or timezone.utc)
        text = f"{self.settings.BOT_AUTHOR_NAME} 응답: {context.last_message.content.text}"
        if context.knowledge_references:
            text += f" | {context.knowledge_references[0].content}"
        yield Message(
            message_id=f"{context.last_message.message_id}-reply",
            channel=context.last_message.channel,
            author=Author(
                author_id=self.settings.BOT_AUTHOR_ID,
                author_name=self.settings.BOT_AUTHOR_NAME,
            ),
            content=MessageContent(text=text, attachments=[]),
            timestamp=now,
        )


@pytest.mark.asyncio
async def test_handle_new_message_generates_streaming_reply():
    # 실제 파이프라인 구성 요소를 흉내 내어 응답이 스트림으로 생성되는지 검증한다.
    settings = Settings()
    seed_memory = MemoryItem(
        memory_id="seed-memory",
        channel_id="test",
        kind="ephemeral",
        content="최근에 날씨에 관심이 많았어",
        importance=1,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    repository = InMemoryMessageRepository()
    memory_store = InMemoryMemoryStore([seed_memory])
    memory_extractor = QuietMemoryExtractor()
    retrieval_planner = FixedRetrievalPlanner()
    retrieval_executor = FakeRetrievalExecutor()
    collector_factory = FakeCollectorFactory()
    retrieval_post_processor = FakeRetrievalPostProcessor()
    reply_generator = StaticReplyGenerator(settings)
    context_builder = ReplyContextBuilder(repository, memory_store, settings)

    tools = PipelineTools(
        settings=settings,
        message_repository=cast(MessageRepository, repository),
        memory_store=cast(MemoryStore, memory_store),
        memory_extractor=cast(ConversationMemoryExtractor, memory_extractor),
        retrieval_planner=cast(RetrievalPlanner, retrieval_planner),
        retrieval_executor=cast(RetrievalExecutor, retrieval_executor),
        retrieval_collector_factory=cast(RetrievalResultCollectorFactory, collector_factory),
        retrieval_post_processor=cast(RetrievalPostProcessor, retrieval_post_processor),
        reply_generator=cast(ReplyGenerator, reply_generator),
        context_builder=context_builder,
        middlewares=[],
        retrieval_timeout_seconds=1.0,
    )

    step_registry = StepRegistry()
    step_registry.register_many(DEFAULT_STEPS)
    pipeline = ChatPipeline(
        tools=tools,
        step_registry=step_registry,
        step_order=default_step_order(),
        reply_saver=repository.save,
    )

    handler = NewMessageHandler(pipeline)

    incoming = Message(
        message_id=str(uuid.uuid4()),
        channel=Channel(channel_id="test", channel_name="테스트"),
        author=Author(author_id="user", author_name="테스터"),
        content=MessageContent(text="/내일 날씨 어때?"),
        timestamp=datetime.now(timezone.utc),
    )

    replies: list[Message] = []
    async for reply in handler.handle(incoming):
        replies.append(reply)

    assert repository.saved, "incoming message should be stored"
    assert replies, "the handler should emit at least one reply"
    assert "테스트 지식" in replies[0].content.text
    assert any(item.channel_id == "test" for item in memory_store._items)
