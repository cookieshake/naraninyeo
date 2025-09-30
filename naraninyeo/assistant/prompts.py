"""Prompt payloads and templates powering the assistant's LLM calls."""

from dataclasses import dataclass
from textwrap import dedent
from typing import Callable, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from naraninyeo.assistant.models import Message, ReplyContext
from naraninyeo.settings import Settings

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
