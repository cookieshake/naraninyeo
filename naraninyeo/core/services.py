"""Self-contained helpers that power the chat assistant.

The goal of this module is to keep all moving parts in one place so that
new teammates can read from top to bottom and understand how the system
works: prompt templates feed into LLM agents, which then support memory,
retrieval, and message storage services.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from textwrap import dedent
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Generic,
    Iterable,
    Literal,
    Protocol,
    Sequence,
    TypeVar,
    cast,
    runtime_checkable,
)
from urllib.parse import urljoin, urlparse

import dateparser
import httpx
import nanoid
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter
from motor.motor_asyncio import AsyncIOMotorDatabase
from opentelemetry.trace import get_tracer
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent as _PydanticAgent
from pydantic_ai import NativeOutput, PromptedOutput, TextOutput, ToolOutput
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.openai import OpenAIModel, OpenAIModelSettings
from pydantic_ai.output import OutputSpec
from pydantic_ai.providers.openrouter import OpenRouterProvider
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qmodels

from naraninyeo.core.models import (
    ChatHistoryRef,
    MemoryItem,
    Message,
    ReplyContext,
    RetrievalPlan,
    RetrievalResult,
    RetrievalStatus,
    RetrievalStatusReason,
    UrlRef,
)
from naraninyeo.embeddings import TextEmbedder
from naraninyeo.settings import Settings

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

T = TypeVar("T")


class PromptPayload(BaseModel):
    """Base prompt input that can include dataclass fields."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def render(self) -> str:  # pragma: no cover - concrete subclasses override
        raise NotImplementedError


@dataclass(frozen=True)
class PromptTemplate(Generic[T]):
    name: str
    system_builder: Callable[[Settings], str]
    user_builder: Callable[[T], str]

    def system_prompt(self, settings: Settings) -> str:
        return dedent(self.system_builder(settings)).strip()

    def user_prompt(self, payload: T) -> str:
        return dedent(self.user_builder(payload)).strip()


class PlannerPrompt(PromptPayload):
    context: ReplyContext

    def render(self) -> str:
        memory_text = (
            "\n".join([m.content for m in (self.context.short_term_memory or [])])
            if getattr(self.context, "short_term_memory", None)
            else "(없음)"
        )
        history = "\n".join([msg.text_repr for msg in self.context.latest_history])
        return dedent(
            f"""
            직전 대화 기록:
            ---
            {history}
            ---

            새로 들어온 메시지:
            {self.context.last_message.text_repr}

            단기 기억(있다면 우선 고려):
            ---
            {memory_text}
            ---

            위 메시지에 답하기 위해 어떤 종류의 검색을 어떤 검색어로 해야할까요?
            참고할만한 예전 대화 기록을 활용하여 더 정확한 검색 계획을 수립하세요.
            """
        ).strip()


class ReplyPrompt(PromptPayload):
    context: ReplyContext
    bot_name: str

    def render(self) -> str:
        knowledge_text = []
        for ref in self.context.knowledge_references:
            text = f"[출처: {ref.source_name}"
            if ref.timestamp:
                text += f", {ref.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            text += f"]\n{ref.content}"
            knowledge_text.append(text)

        memory_text = [f"- {m.content}" for m in (self.context.short_term_memory or [])]
        history = "\n".join([msg.text_repr for msg in self.context.latest_history])
        return dedent(
            f"""
            참고할 만한 정보
            ---
            [상황]
            현재 시각은 {self.context.environment.timestamp.strftime("%Y-%m-%d %H:%M:%S")}입니다.
            현재 위치는 {self.context.environment.location}입니다.

            [단기 기억]
            {"\n".join(memory_text) if memory_text else "(없음)"}

            [검색/지식]
            {"\n\n".join(knowledge_text) if knowledge_text else "(없음)"}
            ---

            직전 대화 기록:
            ---
            {history}
            ---

            마지막으로 들어온 메시지:
            {self.context.last_message.text_repr}

            [응답 생성 우선순위]
            1) 직전 대화의 흐름과 톤에 자연스럽게 이어질 것
            2) 마지막 메시지의 의도에 정확히 답할 것
            3) 참고 정보는 보조로만 사용하고, 대화 맥락과 충돌하면 참고 정보를 과감히 무시할 것
            - 주제 일탈 금지. 사용자가 원하지 않으면 새로운 화제를 시작하지 말 것.

            위 내용을 바탕으로 '{self.bot_name}'의 응답을 생성하세요.

            반드시 메시지 내용만 작성하세요.
            "시간 이름: 내용" 형식이나 "나란잉여:" 같은 접두사를 절대 사용하지 마세요.
            바로 답변 내용으로 시작하세요.
            짧고 간결하게, 핵심만 요약해서 전달하세요. 불필요한 미사여구나 설명은 생략하세요.
            참고 정보에 끌려가서 대화 흐름을 깨지 않도록 주의하세요.
            """
        ).strip()


class MemoryPrompt(PromptPayload):
    message: Message
    history: list[Message]

    def render(self) -> str:
        recent = "\n".join([m.text_repr for m in self.history[-10:]])
        return dedent(
            f"""
            최근 대화 기록:
            ---
            {recent}
            ---

            새 메시지:
            {self.message.text_repr}
            """
        ).strip()


class ExtractorPrompt(PromptPayload):
    markdown: str
    query: str

    def render(self) -> str:
        return dedent(
            f"""
            [검색 쿼리]
            {self.query}

            [문서 내용]
            {self.markdown}
            """
        ).strip()


def _planner_system(_: Settings) -> str:
    return """
    당신은 사용자의 질문에 답하기 위해 어떤 정보를 검색해야 할지 계획하는 AI입니다.
    사용자의 질문, 대화 기록, 단기 기억을 바탕으로 아래 타입 중 필요한 것을 선택하여 계획하세요.

    사용 가능한 검색 타입:
    - naver_news: 최신 뉴스를 찾을 때
    - naver_blog: 개인 경험/후기를 찾을 때
    - naver_web: 일반 웹 페이지 전반 탐색
    - naver_doc: 학술/문서 기반 정보
    - wikipedia: 일반 상식/개념/사전적 정보
    - chat_history: 과거 대화 내용 탐색

    필요 없으면 빈 배열을 반환하고, 필요한 경우 여러 타입을 조합할 수 있습니다.
    각 계획에는 search_type과 적절한 query를 포함하세요.
    """


def _reply_system(settings: Settings) -> str:
    return f"""
    [정체성]
    - 이름: {settings.BOT_AUTHOR_NAME}
    - 역할: 생각을 넓혀주는 대화 파트너
    - 성격: 중립적이고 친근함

    [답변 규칙]
    - 간결하고 핵심만 말함
    - 한쪽에 치우치지 않고 다양한 관점 제시
    - 무조건 한국어 반말 사용
    - "검색 결과에 따르면" 같은 표현 절대 사용 금지
    - "시간 이름: 메시지" 형식 사용 금지
    - 대화 맥락 우선: 직전 대화의 흐름과 톤을 최우선으로 맞출 것
    - 참고 정보는 보조자료: 대화 맥락과 충돌하면 참고 정보를 과감히 무시할 것
    - 주제 탈 금지: 사용자가 원치 않으면 새로운 화제를 열지 말 것
    """


def _memory_system(_: Settings) -> str:
    return """
    다음 대답에 유용할 수 있는 단기 기억 후보를 0~3개 추출하세요.

    각 항목은 아래 속성을 포함해야 합니다.
    - content: 기억 내용 (200자 이하)
    - importance: 1~5 사이 정수
    - kind: "ephemeral", "persona", "task" 중 하나
    - ttl_hours: 1~48 사이 정수 또는 null
    """


def _extractor_system(_: Settings) -> str:
    return """
    주어진 문서를 읽고, 검색 쿼리와 가장 잘 맞는 핵심 문장을 3줄 이하로 요약하세요.
    """


PLANNER_PROMPT = PromptTemplate[PlannerPrompt](
    name="planner",
    system_builder=_planner_system,
    user_builder=lambda payload: payload.render(),
)

REPLY_PROMPT = PromptTemplate[ReplyPrompt](
    name="reply",
    system_builder=_reply_system,
    user_builder=lambda payload: payload.render(),
)

MEMORY_PROMPT = PromptTemplate[MemoryPrompt](
    name="memory",
    system_builder=_memory_system,
    user_builder=lambda payload: payload.render(),
)

EXTRACTOR_PROMPT = PromptTemplate[ExtractorPrompt](
    name="extractor",
    system_builder=_extractor_system,
    user_builder=lambda payload: payload.render(),
)


# ---------------------------------------------------------------------------
# LLM tooling
# ---------------------------------------------------------------------------

TIn = TypeVar("TIn")
TOut = TypeVar("TOut")


class LLMProvider:
    """Simple interface so plugins can supply custom providers."""

    def create_model(self, model_name: str) -> OpenAIModel:  # pragma: no cover
        raise NotImplementedError


class OpenRouterLLMProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._provider = OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)

    def create_model(self, model_name: str) -> OpenAIModel:
        return OpenAIModel(model_name=model_name, provider=self._provider)


ProviderFactory = Callable[[Settings], LLMProvider]


class LLMProviderRegistry:
    """Keeps track of available LLM providers by name."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderFactory] = {}
        self.register("openrouter", lambda settings: OpenRouterLLMProvider(settings))

    def register(self, name: str, factory: ProviderFactory) -> None:
        self._providers[name] = factory

    def build(self, name: str, settings: Settings) -> LLMProvider:
        if name not in self._providers:
            raise KeyError(f"Unknown LLM provider: {name}")
        return self._providers[name](settings)


@dataclass(frozen=True)
class LLMScript(Generic[TIn, TOut]):
    name: str
    model_setting: str
    timeout_setting: str
    prompt: PromptTemplate[TIn]
    output: OutputSpec[TOut]


class LLMTool(Generic[TIn, TOut]):
    """Wraps a pydantic-ai agent and a prompt template."""

    def __init__(self, agent: _PydanticAgent[Any, TOut], prompt: PromptTemplate[TIn]):
        self._agent = agent
        self._prompt = prompt

    async def run(self, payload: TIn) -> TOut:
        prompt = self._prompt.user_prompt(payload)
        result = await self._agent.run(prompt)
        return result.output

    async def stream_text(self, payload: TIn, *, delta: bool = True) -> AsyncIterator[str]:
        prompt = self._prompt.user_prompt(payload)
        async with self._agent.run_stream(prompt) as stream:
            async for chunk in stream.stream_text(delta=delta):
                yield chunk


class LLMAgentFactory:
    """Builds ready-to-use tools for reply, planning, and memory extraction."""

    def __init__(self, settings: Settings, provider_registry: LLMProviderRegistry | None = None):
        provider_name = getattr(settings, "LLM_PROVIDER", "openrouter")
        registry = provider_registry or LLMProviderRegistry()
        try:
            self._provider = registry.build(provider_name, settings)
        except KeyError:
            self._provider = OpenRouterLLMProvider(settings)
        self.settings = settings

    def _select_output_spec(self, output_spec: OutputSpec[TOut], model: OpenAIModel) -> OutputSpec[TOut]:
        if output_spec is str:
            return output_spec  # type: ignore[return-value]
        if isinstance(output_spec, (NativeOutput, PromptedOutput, TextOutput, ToolOutput)):
            return output_spec
        profile = getattr(model, "profile", None)
        if getattr(profile, "supports_json_schema_output", False):
            return NativeOutput(output_spec)  # type: ignore[arg-type]
        return output_spec

    def _build_agent(
        self,
        script: LLMScript[TIn, TOut],
        output_override: OutputSpec[Any] | None = None,
    ) -> _PydanticAgent[Any, Any]:
        model_name = getattr(self.settings, script.model_setting)
        timeout = getattr(self.settings, script.timeout_setting)
        model = self._provider.create_model(model_name)
        desired_output: OutputSpec[Any] = output_override or script.output
        output_spec = self._select_output_spec(desired_output, model)
        return _PydanticAgent(
            model=model,
            output_type=output_spec,
            instrument=InstrumentationSettings(event_mode="logs"),
            model_settings=OpenAIModelSettings(timeout=int(timeout), extra_body={"reasoning": {"effort": "minimal"}}),
            system_prompt=dedent(script.prompt.system_prompt(self.settings)).strip(),
        )

    def tool(
        self,
        script: LLMScript[TIn, TOut],
        *,
        output_override: OutputSpec[Any] | None = None,
    ) -> LLMTool[TIn, Any]:
        agent = self._build_agent(script, output_override)
        return LLMTool(agent, script.prompt)

    def reply_tool(self) -> LLMTool[Any, str]:
        return self.tool(REPLY_SCRIPT)

    def planner_tool(self) -> LLMTool[Any, list[RetrievalPlan]]:
        return self.tool(PLANNER_SCRIPT)

    def memory_tool(self, *, output_type: OutputSpec[Any]) -> LLMTool[Any, Any]:
        return self.tool(MEMORY_SCRIPT, output_override=output_type)

    def extractor_tool(self, *, output_type: OutputSpec[Any]) -> LLMTool[Any, Any]:
        return self.tool(EXTRACTOR_SCRIPT, output_override=output_type)


def text() -> OutputSpec[str]:
    return str


def native(tp: type[TOut]) -> OutputSpec[TOut]:
    return NativeOutput(tp)


def tool(
    tp: type[TOut],
    *,
    name: str | None = None,
    description: str | None = None,
    strict: bool | None = None,
) -> OutputSpec[TOut]:
    return ToolOutput(tp, name=name, description=description, strict=strict)


def prompted(
    outputs: Sequence[type[TOut]],
    *,
    name: str | None = None,
    description: str | None = None,
) -> OutputSpec[TOut]:
    return PromptedOutput(list(outputs), name=name, description=description)


def list_of(tp: type[TOut]) -> OutputSpec[list[TOut]]:
    return cast(OutputSpec[list[TOut]], list[tp])


def union_of(*types: type[TOut]) -> OutputSpec[TOut]:
    return cast(OutputSpec[TOut], list(types))


def text_fn(fn: Callable[[str], TOut]) -> OutputSpec[TOut]:
    return TextOutput(fn)


REPLY_SCRIPT = LLMScript[Any, str](
    name="reply",
    model_setting="REPLY_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_REPLY",
    prompt=REPLY_PROMPT,
    output=text(),
)

PLANNER_SCRIPT = LLMScript[Any, list[RetrievalPlan]](
    name="planner",
    model_setting="PLANNER_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_PLANNER",
    prompt=PLANNER_PROMPT,
    output=list_of(RetrievalPlan),
)

MEMORY_SCRIPT = LLMScript[Any, Any](
    name="memory",
    model_setting="MEMORY_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_MEMORY",
    prompt=MEMORY_PROMPT,
    output=text(),
)

EXTRACTOR_SCRIPT = LLMScript[Any, Any](
    name="extractor",
    model_setting="EXTRACTOR_MODEL_NAME",
    timeout_setting="LLM_TIMEOUT_SECONDS_EXTRACTOR",
    prompt=EXTRACTOR_PROMPT,
    output=text(),
)


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------


@runtime_checkable
class MemoryStore(Protocol):
    async def put(self, items: list[MemoryItem]) -> None: ...

    async def recall(self, *, channel_id: str, limit: int, now: datetime) -> list[MemoryItem]: ...


class MongoMemoryStore:
    def __init__(self, mongodb: AsyncIOMotorDatabase):
        self._collection = mongodb["memory"]
        self._index_ready = False

    async def put(self, items: list[MemoryItem]) -> None:
        if not items:
            return
        if not self._index_ready:
            try:
                await self._collection.create_index("expires_at", expireAfterSeconds=0)
            except Exception:
                pass
            self._index_ready = True
        for item in items:
            await self._collection.update_one(
                {"memory_id": item.memory_id},
                {"$set": item.model_dump()},
                upsert=True,
            )

    async def recall(self, *, channel_id: str, limit: int, now: datetime) -> list[MemoryItem]:
        cursor = (
            self._collection.find(
                {
                    "channel_id": channel_id,
                    "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}],
                }
            )
            .sort([("importance", -1), ("created_at", -1)])
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [MemoryItem.model_validate(doc) for doc in docs]

    async def evict_expired(self, *, now: datetime) -> int:
        result = await self._collection.delete_many({"expires_at": {"$lte": now}})
        return int(result.deleted_count)


class LLMExtractionItem(BaseModel):
    content: str = Field(min_length=1, max_length=200)
    importance: int = Field(default=1, ge=1, le=5)
    kind: Literal["ephemeral", "persona", "task"] = "ephemeral"
    ttl_hours: int | None = Field(default=None, ge=1, le=48)


class LLMMemoryExtractor:
    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory):
        self.settings = settings
        self.tool: LLMTool[MemoryPrompt, list[LLMExtractionItem]] = llm_factory.memory_tool(
            output_type=list_of(LLMExtractionItem)
        )

    async def extract_from_message(self, message: Message, history: list[Message]) -> list[MemoryItem]:
        if (message.content.text or "").strip().startswith("/"):
            return []

        prompt = MemoryPrompt(message=message, history=history)

        try:
            items = await self.tool.run(prompt)
        except Exception:
            return []

        now = datetime.now(timezone.utc)
        output: list[MemoryItem] = []
        for item in (items or [])[:3]:
            ttl = item.ttl_hours if item.ttl_hours is not None else self.settings.MEMORY_TTL_HOURS
            expires = now + timedelta(hours=int(ttl))
            output.append(
                MemoryItem(
                    memory_id=str(uuid.uuid4()),
                    channel_id=message.channel.channel_id,
                    kind=item.kind,
                    content=item.content.strip(),
                    importance=item.importance,
                    created_at=now,
                    expires_at=expires,
                )
            )
        return output


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------


@runtime_checkable
class MessageRepository(Protocol):
    async def save(self, message: Message) -> None: ...

    async def get_surrounding_messages(self, message: Message, before: int, after: int) -> list[Message]: ...

    async def search_similar_messages(self, channel_id: str, keyword: str, limit: int) -> list[Message]: ...


class MongoQdrantMessageRepository:
    def __init__(
        self,
        mongodb: AsyncIOMotorDatabase,
        qdrant_client: AsyncQdrantClient,
        text_embedder: TextEmbedder,
    ) -> None:
        self._collection = mongodb["messages"]
        self._qdrant_client = qdrant_client
        self._qdrant_collection = "naraninyeo-messages"
        self._text_embedder = text_embedder

    @get_tracer(__name__).start_as_current_span("save message")
    async def save(self, message: Message) -> None:
        tasks = [
            self._collection.update_one(
                {"message_id": message.message_id},
                {"$set": message.model_dump()},
                upsert=True,
            ),
            self._qdrant_client.upsert(
                collection_name=self._qdrant_collection,
                points=[
                    qmodels.PointStruct(
                        id=self._str_to_64bit(message.message_id),
                        vector=(await self._text_embedder.embed([message.content.text]))[0],
                        payload={
                            "message_id": message.message_id,
                            "channel_id": message.channel.channel_id,
                            "text": message.content.text,
                            "timestamp": message.timestamp.isoformat(),
                            "author": message.author.author_name,
                        },
                    )
                ],
            ),
        ]
        await asyncio.gather(*tasks)

    @get_tracer(__name__).start_as_current_span("load message")
    async def load(self, message_id: str) -> Message | None:
        document = await self._collection.find_one({"message_id": message_id})
        return Message.model_validate(document) if document else None

    @get_tracer(__name__).start_as_current_span("get closest message by timestamp")
    async def get_closest_by_timestamp(self, channel_id: str, timestamp: float) -> Message | None:
        document = await self._collection.find_one(
            {"channel.channel_id": channel_id, "timestamp": {"$lte": timestamp}},
            sort=[("timestamp", -1)],
        )
        return Message.model_validate(document) if document else None

    @get_tracer(__name__).start_as_current_span("get surrounding messages")
    async def get_surrounding_messages(self, message: Message, before: int = 5, after: int = 5) -> list[Message]:
        tasks = []
        if before > 0:
            tasks.append(
                self._collection.find(
                    {
                        "channel.channel_id": message.channel.channel_id,
                        "message_id": {"$lt": message.message_id},
                    }
                )
                .sort("timestamp", -1)
                .limit(before)
                .to_list(length=before)
            )
        if after > 0:
            tasks.append(
                self._collection.find(
                    {
                        "channel.channel_id": message.channel.channel_id,
                        "message_id": {"$gt": message.message_id},
                    }
                )
                .sort("timestamp", 1)
                .limit(after)
                .to_list(length=after)
            )

        results = await asyncio.gather(*tasks)
        messages = [message]
        for result in results:
            messages.extend(Message.model_validate(doc) for doc in result if doc)
        messages.sort(key=lambda m: m.timestamp)
        return messages

    @get_tracer(__name__).start_as_current_span("search similar messages")
    async def search_similar_messages(self, channel_id: str, keyword: str, limit: int) -> list[Message]:
        qdrant_result = await self._qdrant_client.query_points(
            collection_name=self._qdrant_collection,
            query=(await self._text_embedder.embed([keyword]))[0],
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="channel_id",
                        match=qmodels.MatchValue(value=channel_id),
                    )
                ]
            ),
            limit=limit,
        )
        message_ids = [point.payload["message_id"] for point in qdrant_result.points if point.payload is not None]
        loaded = await asyncio.gather(*(self.load(mid) for mid in message_ids))
        return [msg for msg in loaded if msg is not None]

    def _str_to_64bit(self, value: str) -> int:
        return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


# ---------------------------------------------------------------------------
# Retrieval system
# ---------------------------------------------------------------------------


@dataclass
class RetrievalPlanLog:
    plan: RetrievalPlan
    matched: bool


class RetrievalPlanner:
    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory):
        self.settings = settings
        self.tool: LLMTool[PlannerPrompt, list[RetrievalPlan]] = llm_factory.planner_tool()

    @get_tracer(__name__).start_as_current_span("plan retrieval")
    async def plan(self, context: ReplyContext) -> list[RetrievalPlan]:
        prompt = PlannerPrompt(context=context)
        plans = await self.tool.run(prompt)
        logging.debug("Retrieval plans generated: %s", [p.model_dump() for p in plans or []])
        return list(plans or [])


class RetrievalResultCollector:
    """Collects retrieval results in memory for later post-processing."""

    def __init__(self) -> None:
        self._results: dict[str, RetrievalResult] = {}

    async def add(self, item: RetrievalResult) -> None:
        self._results[item.result_id] = item

    async def snapshot(self) -> list[RetrievalResult]:
        return list(self._results.values())


class RetrievalResultCollectorFactory:
    def create(self) -> RetrievalResultCollector:
        return RetrievalResultCollector()


@runtime_checkable
class RetrievalStrategy(Protocol):
    def supports(self, plan: RetrievalPlan) -> bool: ...

    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> None: ...


class RetrievalExecutor:
    def __init__(self, max_concurrency: int | None = None) -> None:
        self._strategies: list[RetrievalStrategy] = []
        self._semaphore = asyncio.Semaphore(max_concurrency or 999999)

    def register(self, strategy: RetrievalStrategy) -> None:
        if not isinstance(strategy, RetrievalStrategy):
            raise TypeError("Strategy must define 'supports' and 'execute' methods")
        self._strategies.append(strategy)

    @property
    def strategies(self) -> list[RetrievalStrategy]:
        return list(self._strategies)

    async def execute(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> list[RetrievalPlanLog]:
        tasks: list[asyncio.Task[None]] = []
        logs: list[RetrievalPlanLog] = []
        try:
            for plan in plans:
                matched = False
                for strategy in self._strategies:
                    if strategy.supports(plan):
                        matched = True

                        async def run_with_sem(s=strategy, p=plan) -> None:
                            async with self._semaphore:
                                await s.execute(p, context, collector)

                        tasks.append(asyncio.create_task(run_with_sem()))
                        break
                logs.append(RetrievalPlanLog(plan=plan, matched=matched))
                if not matched:
                    logging.warning("No executor found for plan: %s", plan.model_dump())
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logging.info("A retrieval strategy failed", exc_info=result)
        except asyncio.CancelledError:
            logging.info("Retrieval tasks were cancelled, so some results may be missing.")
        return logs

    async def execute_with_timeout(
        self,
        plans: list[RetrievalPlan],
        context: ReplyContext,
        timeout_seconds: float,
        collector: RetrievalResultCollector,
    ) -> list[RetrievalPlanLog]:
        try:
            return await asyncio.wait_for(
                self.execute(plans, context, collector),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logging.info("Retrieval execution timed out; returning partial results")
            return []


class HeuristicRetrievalRanker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def score(self, item: RetrievalResult) -> float:
        score = 1.0
        search_type = getattr(item.plan, "search_type", None)
        score += float(self.settings.RANK_WEIGHTS.get(search_type or "", 0.0))
        ts = item.source_timestamp
        if isinstance(ts, datetime):
            try:
                now = datetime.now(ts.tzinfo or timezone.utc)
                window = timedelta(hours=int(self.settings.RECENCY_WINDOW_HOURS))
                age = now - ts
                if age <= window:
                    fraction = max(0.0, 1.0 - age.total_seconds() / window.total_seconds())
                    score += float(self.settings.RECENCY_BONUS_MAX) * fraction
            except Exception:
                pass
        return score


class RetrievalPostProcessor:
    def __init__(self, settings: Settings, ranker: HeuristicRetrievalRanker):
        self.settings = settings
        self.ranker = ranker

    def process(self, results: list[RetrievalResult], context: ReplyContext) -> list[RetrievalResult]:
        filtered = [r for r in results if r.content and r.content.strip()]
        seen: set[tuple[str, str]] = set()
        deduped: list[RetrievalResult] = []
        for item in filtered:
            try:
                ref_attr = getattr(item.ref, "as_text", None)
                if isinstance(ref_attr, str):
                    ref_text = ref_attr
                elif callable(ref_attr):
                    ref_text = str(ref_attr())
                else:
                    ref_text = str(item.ref)
            except Exception:
                ref_text = str(item.ref)
            key = (ref_text, item.content.strip())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        try:
            deduped.sort(key=lambda r: self.ranker.score(r), reverse=True)
        except Exception:
            deduped.sort(key=lambda r: r.result_id)
        return deduped[: max(1, self.settings.MAX_KNOWLEDGE_REFERENCES)]


class ChatHistoryStrategy:
    def __init__(self, message_repository: MongoQdrantMessageRepository):
        self.message_repository = message_repository

    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type == "chat_history"

    @get_tracer(__name__).start_as_current_span("execute chat history retrieval")
    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> None:
        messages = await self.message_repository.search_similar_messages(
            channel_id=context.last_message.channel.channel_id,
            keyword=plan.query,
            limit=3,
        )
        chunks = [
            self.message_repository.get_surrounding_messages(message=message, before=3, after=3) for message in messages
        ]
        for task in asyncio.as_completed(chunks):
            chunk = await task
            if not chunk:
                continue
            ref = ChatHistoryRef(value=chunk)
            await collector.add(
                RetrievalResult(
                    plan=plan,
                    result_id=nanoid.generate(),
                    content=ref.as_text,
                    ref=ref,
                    status=RetrievalStatus.SUCCESS,
                    status_reason=RetrievalStatusReason.SUCCESS,
                    source_name=f"chat_history_{chunk[-1].timestamp_str}",
                    source_timestamp=chunk[-1].timestamp if chunk else None,
                )
            )


class Crawler:
    def __init__(self) -> None:
        self.markdown_converter = MarkdownConverter()

    @get_tracer(__name__).start_as_current_span("get markdown from url")
    async def get_markdown_from_url(self, url: str) -> str:
        async with httpx.AsyncClient() as client:
            last_exc: Exception | None = None
            for _ in range(3):
                try:
                    response = await client.get(
                        url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        },
                        follow_redirects=True,
                        timeout=20.0,
                    )
                    response.raise_for_status()
                    html_text = response.text
                    soup = BeautifulSoup(html_text, "html.parser")
                    break
                except Exception as exc:
                    last_exc = exc
                    await asyncio.sleep(0.5)
            else:
                logging.info("Failed to fetch url after retries", exc_info=last_exc)
                return ""

            iframes = [iframe for iframe in soup.find_all("iframe") if isinstance(iframe.get("src"), str)]  # pyright: ignore[reportAttributeAccessIssue]
            if iframes:
                async with httpx.AsyncClient() as iframe_client:
                    iframe_links = [urljoin(url, iframe.get("src")) for iframe in iframes]  # pyright: ignore[reportArgumentType, reportAttributeAccessIssue]
                    iframe_htmls = await asyncio.gather(
                        *(iframe_client.get(link) for link in iframe_links),
                        return_exceptions=True,
                    )
                for iframe, iframe_resp in zip(iframes, iframe_htmls, strict=False):
                    if isinstance(iframe_resp, BaseException):
                        logging.warning(
                            "Failed to retrieve iframe %s: %s",
                            iframe.get("src"),
                            iframe_resp,  # pyright: ignore[reportAttributeAccessIssue]
                        )
                        continue
                    iframe_soup = BeautifulSoup(iframe_resp.text, "html.parser")
                    iframe.replace_with(iframe_soup)

            for tag in ["a", "button", "iframe"]:
                for element in soup.find_all(tag):
                    element.decompose()
            return self.markdown_converter.convert_soup(soup)


class ExtractionResult(BaseModel):
    content: str
    is_relevant: bool | None


class Extractor:
    def __init__(self, settings: Settings, crawler: Crawler, llm_factory: LLMAgentFactory) -> None:
        self.settings = settings
        self.crawler = crawler
        self.tool: LLMTool[ExtractorPrompt, ExtractionResult] = llm_factory.extractor_tool(
            output_type=native(ExtractionResult)
        )

    async def extract(
        self,
        url: str,
        plan: RetrievalPlan,
    ) -> ExtractionResult | None:
        markdown = await self.crawler.get_markdown_from_url(url)
        if not markdown:
            return None
        prompt = ExtractorPrompt(markdown=markdown, query=plan.query)
        try:
            return await self.tool.run(prompt)
        except Exception as exc:  # pragma: no cover - network/LLM failures are noisy already
            logging.debug("Extractor failed", exc_info=exc)
            return None


class NaverSearchStrategy:
    def __init__(self, settings: Settings, llm_factory: LLMAgentFactory) -> None:
        self.settings = settings
        self.extractor = Extractor(settings, Crawler(), llm_factory)

    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type.startswith("naver_")

    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> None:
        results = await self._search(plan)
        tasks = [self._handle_result(plan, collector, item) for item in results]
        await asyncio.gather(*tasks)

    async def _search(self, plan: RetrievalPlan) -> list[dict[str, str]]:
        base_url = "https://openapi.naver.com/v1/search/"
        match plan.search_type:
            case "naver_news":
                endpoint = "news.json"
            case "naver_blog":
                endpoint = "blog.json"
            case "naver_web":
                endpoint = "webkr.json"
            case "naver_doc":
                endpoint = "doc.json"
            case _:
                raise ValueError(f"Unsupported search type: {plan.search_type}")
        url = f"{base_url}{endpoint}"
        headers = {
            "X-Naver-Client-Id": self.settings.NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": self.settings.NAVER_CLIENT_SECRET,
        }
        params = {"query": plan.query, "display": 5}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
        return payload.get("items", [])

    async def _handle_result(
        self,
        plan: RetrievalPlan,
        collector: RetrievalResultCollector,
        item: dict[str, str],
    ) -> None:
        link = item.get("link") or item.get("originallink")
        if not link:
            return
        cleaned_title = html.unescape(re.sub("<.*?>", "", item.get("title", "")).strip())
        summary = html.unescape(re.sub("<.*?>", "", item.get("description", "")).strip())
        extraction = await self.extractor.extract(link, plan)
        if not extraction or extraction.is_relevant is False:
            return
        content = summary
        if extraction.content:
            content = f"{summary}\n{extraction.content}" if summary else extraction.content
        timestamp = self._parse_datetime(item.get("pubDate"))
        await collector.add(
            RetrievalResult(
                plan=plan,
                result_id=nanoid.generate(),
                content=content,
                ref=UrlRef(value=link),
                status=RetrievalStatus.SUCCESS,
                status_reason=RetrievalStatusReason.SUCCESS,
                source_name=cleaned_title or urlparse(link).netloc,
                source_timestamp=timestamp,
            )
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = dateparser.parse(value)
        if parsed is None:
            return None
        return parsed.astimezone(timezone.utc)


class WikipediaStrategy:
    def supports(self, plan: RetrievalPlan) -> bool:
        return plan.search_type == "wikipedia"

    async def execute(
        self,
        plan: RetrievalPlan,
        context: ReplyContext,
        collector: RetrievalResultCollector,
    ) -> None:
        summary = await self._summary(plan.query)
        if not summary:
            return
        await collector.add(
            RetrievalResult(
                plan=plan,
                result_id=nanoid.generate(),
                content=summary,
                ref=UrlRef(value=f"https://ko.wikipedia.org/wiki/{plan.query}"),
                status=RetrievalStatus.SUCCESS,
                status_reason=RetrievalStatusReason.SUCCESS,
                source_name="wikipedia",
                source_timestamp=datetime.now(timezone.utc),
            )
        )

    async def _summary(self, query: str) -> str | None:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://ko.wikipedia.org/api/rest_v1/page/summary/" + query,
                timeout=10,
            )
        if response.status_code != 200:
            return None
        data = response.json()
        extract = data.get("extract")
        if not extract:
            return None
        return extract


class RetrievalLogger:
    """Simple observer that records which plans were matched."""

    def __init__(self) -> None:
        self.entries: list[RetrievalPlanLog] = []

    def record(self, entries: Iterable[RetrievalPlanLog]) -> None:
        self.entries.extend(entries)
