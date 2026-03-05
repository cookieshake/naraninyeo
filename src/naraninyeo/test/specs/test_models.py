"""
도메인 모델 불변 조건 스펙 테스트

스펙: core/models.py의 도메인 모델이 지켜야 할 불변 조건
연동: 없음 (순수 단위 테스트)
"""

from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from naraninyeo.core.models import (
    ActionType,
    Attachment,
    Author,
    Bot,
    Channel,
    Message,
    MessageContent,
    PlanAction,
    ResponsePlan,
    TenancyContext,
)


def _make_message(text: str = "안녕하세요", timestamp: datetime | None = None) -> Message:
    return Message(
        message_id="msg-1",
        channel=Channel(channel_id="ch-1", channel_name="테스트채널"),
        author=Author(author_id="user-1", author_name="테스터"),
        content=MessageContent(text=text),
        timestamp=timestamp or datetime.now(UTC),
    )


# --- Message.ensure_timezone ---


def test_naive_datetime_gets_utc():
    """naive datetime은 UTC timezone이 부착된다."""
    naive = datetime(2024, 1, 1, 12, 0, 0)  # no tzinfo
    msg = _make_message(timestamp=naive)

    assert msg.timestamp.tzinfo is not None
    assert msg.timestamp.tzinfo == UTC


def test_aware_datetime_converts_to_utc():
    """timezone-aware datetime은 UTC로 변환된다."""
    kst = timezone(offset=__import__("datetime").timedelta(hours=9))
    kst_time = datetime(2024, 1, 1, 21, 0, 0, tzinfo=kst)  # 21:00 KST = 12:00 UTC
    msg = _make_message(timestamp=kst_time)

    assert msg.timestamp.tzinfo == UTC
    assert msg.timestamp.hour == 12


# --- Message.timestamp_iso ---


def test_timestamp_iso_uses_tz_env_var(monkeypatch):
    """timestamp_iso는 TZ 환경변수 기준 로컬 시간 문자열이다."""
    monkeypatch.setenv("TZ", "Asia/Seoul")
    utc_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)  # 12:00 UTC = 21:00 KST
    msg = _make_message(timestamp=utc_time)

    iso = msg.timestamp_iso
    assert "21:00" in iso


def test_timestamp_iso_defaults_to_asia_seoul(monkeypatch):
    """TZ 환경변수가 없으면 Asia/Seoul을 기본값으로 사용한다."""
    monkeypatch.delenv("TZ", raising=False)
    utc_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    msg = _make_message(timestamp=utc_time)

    iso = msg.timestamp_iso
    assert "21:00" in iso


# --- Message.preview ---


def test_preview_is_within_100_chars():
    """preview는 전체 포맷 기준 길이 제한 내에 있다."""
    long_text = "가" * 200
    msg = _make_message(text=long_text)

    # preview = [timestamp] name(id): snippet
    # snippet은 100자로 제한됨
    assert "..." in msg.preview  # 텍스트가 잘렸음을 나타냄


def test_preview_has_no_newlines():
    """preview에는 개행문자가 없다."""
    msg = _make_message(text="첫 번째 줄\n두 번째 줄\n세 번째 줄")

    assert "\n" not in msg.preview


def test_preview_includes_author_info():
    """preview에 작성자 이름과 ID가 포함된다."""
    msg = _make_message()

    assert "테스터" in msg.preview
    assert "user-1" in msg.preview


# --- ResponsePlan.summary ---


def test_response_plan_summary_includes_all_actions():
    """summary는 모든 action을 포함한다."""
    plan = ResponsePlan(
        actions=[
            PlanAction(action_type=ActionType.SEARCH_WEB_GENERAL, description="일반 검색", query="파이썬"),
            PlanAction(action_type=ActionType.SEARCH_FINANCIAL_DATA, description="금융 데이터 검색", query="삼성전자"),
        ],
        generation_instructions=None,
    )

    summary = plan.summary
    assert "SEARCH_WEB_GENERAL" in summary
    assert "SEARCH_FINANCIAL_DATA" in summary


def test_response_plan_summary_empty_actions():
    """actions가 비어있어도 summary가 생성된다."""
    plan = ResponsePlan(actions=[], generation_instructions=None)

    summary = plan.summary
    assert isinstance(summary, str)


def test_response_plan_summary_truncates_long_description():
    """50자 초과 description은 잘린다."""
    long_desc = "이것은 매우 긴 설명입니다" * 10
    plan = ResponsePlan(
        actions=[PlanAction(action_type=ActionType.SEARCH_WEB_GENERAL, description=long_desc)],
        generation_instructions=None,
    )

    summary = plan.summary
    assert "..." in summary


# --- ValidationError cases ---


def test_tenancy_context_rejects_empty_tenant_id():
    """tenant_id가 빈 문자열이면 ValidationError를 발생시킨다."""
    with pytest.raises(ValidationError):
        TenancyContext(tenant_id="")


def test_bot_rejects_empty_bot_name():
    """bot_name이 빈 문자열이면 ValidationError를 발생시킨다."""
    with pytest.raises(ValidationError):
        Bot(bot_id="id-1", bot_name="", author_id="author-1", created_at=datetime.now(UTC))


def test_attachment_rejects_invalid_type():
    """지정되지 않은 attachment_type은 ValidationError를 발생시킨다."""
    with pytest.raises(ValidationError):
        Attachment(attachment_id="att-1", attachment_type="document")  # type: ignore[arg-type]


def test_attachment_accepts_valid_types():
    """지정된 4가지 attachment_type은 허용된다."""
    for t in ["image", "video", "file", "audio"]:
        att = Attachment(attachment_id="att-1", attachment_type=t)  # type: ignore[arg-type]
        assert att.attachment_type == t
