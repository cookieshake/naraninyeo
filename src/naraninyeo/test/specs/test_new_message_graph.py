"""
메시지 처리 파이프라인 행동 스펙 테스트

스펙:
- 욕설 메시지 → 파이프라인 즉시 종료 (draft_messages 비어있음)
- 짧은 메시지/단순 패턴 → 정보 수집 생략, 응답 생성
- 일반 메시지 → 정보 수집 → 응답 생성 → 평가 → 최종화
- 최종 상태의 status = "completed"
- 라우팅 로직 (순수 단위 테스트)
연동: 실제 LLM (라우팅 로직은 LLM 불필요)
"""

from datetime import UTC, datetime

import pytest
from dishka import AsyncContainer

from naraninyeo.core.interfaces import (
    Clock,
    FinanceSearch,
    MemoryRepository,
    MessageRepository,
    NaverSearch,
    WebDocumentFetch,
)
from naraninyeo.core.models import (
    Author,
    Bot,
    Channel,
    EvaluationFeedback,
    Message,
    MessageContent,
    TenancyContext,
)
from naraninyeo.graphs.new_message import (
    _SIMPLE_MSG_PATTERN,
    NewMessageGraphContext,
    NewMessageGraphState,
    new_message_graph,
    route_after_profanity_check,
    route_based_on_evaluation,
)
from naraninyeo.infrastructure.util.nanoid_generator import NanoidGenerator


def _make_state(text: str, is_profane: bool = False) -> NewMessageGraphState:
    nanoid = NanoidGenerator()
    return NewMessageGraphState(
        current_tctx=TenancyContext(tenant_id="test"),
        current_bot=Bot(
            bot_id=nanoid.generate_id(),
            bot_name="테스트봇",
            author_id="author-1",
            created_at=datetime.now(UTC),
        ),
        memories=[],
        status="processing",
        is_profane=is_profane,
        incoming_message=Message(
            message_id=nanoid.generate_id(),
            channel=Channel(channel_id="ch-1", channel_name="테스트채널"),
            author=Author(author_id="user-1", author_name="테스터"),
            content=MessageContent(text=text),
            timestamp=datetime.now(UTC),
        ),
        latest_history=[],
    )


# --- 라우팅 로직 단위 테스트 (LLM 불필요) ---


@pytest.mark.parametrize("text", ["ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "ㄱㅅ", "안녕", "넵", "응", "ㅇㅋ"])
def test_simple_pattern_matches_short_responses(text: str):
    """단순 응답 패턴이 정규식과 매칭된다."""
    assert _SIMPLE_MSG_PATTERN.match(text), f"'{text}'이 단순 패턴으로 인식되어야 함"


@pytest.mark.parametrize("text", ["삼성전자 주가 알려줘", "오늘 날씨 어때?", "파이썬 문법 알려줘"])
def test_general_query_not_matched_by_simple_pattern(text: str):
    """일반 질문은 단순 패턴에 매칭되지 않는다."""
    assert not _SIMPLE_MSG_PATTERN.match(text), f"'{text}'이 단순 패턴으로 잘못 인식됨"


def test_route_after_profanity_check_returns_end_when_profane():
    """욕설 감지 시 END를 반환한다."""
    from langgraph.graph import END

    state = _make_state("욕설 텍스트", is_profane=True)
    result = route_after_profanity_check(state)

    assert result == END


def test_route_after_profanity_check_skips_gather_for_simple_message():
    """짧은 메시지는 정보 수집을 생략하고 바로 응답 생성으로 간다."""
    state = _make_state("ㅋㅋ")
    result = route_after_profanity_check(state)

    assert result == "generate_response"


def test_route_after_profanity_check_skips_gather_for_short_text():
    """5자 이하 메시지는 정보 수집을 생략한다."""
    state = _make_state("안녕요")
    result = route_after_profanity_check(state)

    assert result == "generate_response"


def test_route_after_profanity_check_goes_to_gather_for_general_query():
    """일반 질문은 정보 수집으로 라우팅된다."""
    state = _make_state("삼성전자 주가 알려줘")
    result = route_after_profanity_check(state)

    assert result == "gather_information"


def test_route_based_on_evaluation_regather():
    """REGATHER 피드백은 정보 수집으로 라우팅된다."""
    state = _make_state("테스트")
    state.latest_evaluation_feedback = EvaluationFeedback.REGATHER

    assert route_based_on_evaluation(state) == "gather_information"


def test_route_based_on_evaluation_generate_again():
    """GENERATE_AGAIN 피드백은 응답 생성으로 라우팅된다."""
    state = _make_state("테스트")
    state.latest_evaluation_feedback = EvaluationFeedback.GENERATE_AGAIN

    assert route_based_on_evaluation(state) == "generate_response"


def test_route_based_on_evaluation_finalize():
    """FINALIZE 피드백은 최종화로 라우팅된다."""
    state = _make_state("테스트")
    state.latest_evaluation_feedback = EvaluationFeedback.FINALIZE

    assert route_based_on_evaluation(state) == "finalize_response"


def test_route_based_on_evaluation_raises_for_unknown():
    """알 수 없는 피드백은 ValueError를 발생시킨다."""
    state = _make_state("테스트")
    state.latest_evaluation_feedback = None

    with pytest.raises(ValueError):
        route_based_on_evaluation(state)


# --- 전체 그래프 통합 스펙 (실제 LLM 사용) ---


@pytest.mark.asyncio
async def test_profane_message_terminates_pipeline(test_container: AsyncContainer):
    """욕설 메시지는 파이프라인을 즉시 종료하여 draft_messages가 비어있다."""
    graph_context = await _make_graph_context(test_container)
    state = _make_state("시발 개새끼야")

    result = await new_message_graph.ainvoke(state, context=graph_context)

    assert result["is_profane"] is True
    assert result["draft_messages"] == []
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_simple_greeting_generates_response_without_gathering(test_container: AsyncContainer):
    """간단한 인사말은 정보 수집 없이 응답을 생성한다."""
    graph_context = await _make_graph_context(test_container)
    state = _make_state("안녕")

    result = await new_message_graph.ainvoke(state, context=graph_context)

    assert result["status"] == "completed"
    assert len(result["draft_messages"]) > 0
    # 정보 수집을 건너뛰었으므로 information_gathering_results가 없거나 비어있음
    assert result["information_gathering_results"] == []


@pytest.mark.asyncio
async def test_general_query_completes_full_pipeline(test_container: AsyncContainer):
    """일반 질문은 전체 파이프라인을 거쳐 응답을 생성한다."""
    graph_context = await _make_graph_context(test_container)
    state = _make_state("파이썬이 뭐야? 간단히 설명해줘")

    result = await new_message_graph.ainvoke(state, context=graph_context)

    assert result["status"] == "completed"
    assert len(result["draft_messages"]) > 0


async def _make_graph_context(container: AsyncContainer) -> NewMessageGraphContext:
    return NewMessageGraphContext(
        clock=await container.get(Clock),
        message_repository=await container.get(MessageRepository),
        memory_repository=await container.get(MemoryRepository),
        naver_search_client=await container.get(NaverSearch),
        finance_search_client=await container.get(FinanceSearch),
        web_document_fetcher=await container.get(WebDocumentFetch),
    )
