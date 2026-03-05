"""
API 엔드포인트 통합 스펙 테스트

스펙:
- GET / → 200 (헬스 체크)
- POST /bots → 봇 생성, GET /bots에서 조회 가능
- POST /new_message (reply_needed=false) → is_final=True, 메시지 저장됨
- POST /new_message (reply_needed=true) → 스트리밍 응답, generated_message 포함 청크
- 존재하지 않는 bot_id → 400 에러
연동: 전체 스택 (testcontainers DB + llama.cpp + 실제 LLM)
"""

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from naraninyeo.api.routers.bot import CreateBotRequest
from naraninyeo.core.models import (
    Author,
    Channel,
    Message,
    MessageContent,
    NewMessageRequest,
)


@pytest.mark.asyncio
async def test_health_check(test_client: TestClient):
    """GET /는 200을 반환한다."""
    response = test_client.get("/")

    assert response.status_code == 200
    assert response.text == "Naraninyeo API is running."


@pytest.mark.asyncio
async def test_create_bot_and_retrieve(test_client: TestClient):
    """POST /bots로 봇을 생성하면 GET /bots에서 조회 가능하다."""
    bot_request = CreateBotRequest(name="스펙테스트봇", author_id="test-author")

    response = test_client.post(
        "/bots",
        content=bot_request.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["bot_name"] == "스펙테스트봇"
    assert "bot_id" in created

    bots = test_client.get("/bots").json()
    assert any(b["bot_id"] == created["bot_id"] for b in bots)


@pytest.mark.asyncio
async def test_new_message_without_reply(test_client: TestClient):
    """reply_needed=false이면 is_final=True이고 generated_message가 없다."""
    bot_id = _get_or_create_bot(test_client)
    payload = _make_new_message_request(bot_id, text="조용히 저장만 해줘", reply_needed=False)

    response = test_client.post(
        "/new_message",
        content=payload.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_final"] is True
    assert body.get("generated_message") is None
    assert body.get("error") is None


@pytest.mark.asyncio
async def test_new_message_with_reply_streams_response(test_client: TestClient):
    """reply_needed=true이면 스트리밍 응답에 generated_message가 포함된 청크가 있다."""
    bot_id = _get_or_create_bot(test_client)
    payload = _make_new_message_request(bot_id, text="안녕! 간단히 인사해줘", reply_needed=True)

    with test_client.stream(
        "POST",
        "/new_message",
        content=payload.model_dump_json(),
        headers={"Content-Type": "application/json"},
    ) as response:
        assert response.status_code == 200
        chunks = [json.loads(line) for line in response.iter_lines() if line]

    assert len(chunks) > 0
    final_chunks = [c for c in chunks if c.get("is_final")]
    assert len(final_chunks) == 1

    message_chunks = [c for c in chunks if c.get("generated_message")]
    assert len(message_chunks) > 0, "generated_message가 포함된 청크가 없음"


@pytest.mark.asyncio
async def test_new_message_with_unknown_bot_returns_error(test_client: TestClient):
    """존재하지 않는 bot_id이면 400 에러를 반환한다."""
    payload = _make_new_message_request("non-existent-bot-id", text="테스트", reply_needed=True)

    response = test_client.post(
        "/new_message",
        content=payload.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    assert body.get("is_final") is True


# --- Helpers ---


def _get_or_create_bot(client: TestClient) -> str:
    bots = client.get("/bots").json()
    if bots:
        return bots[0]["bot_id"]
    bot_request = CreateBotRequest(name="통합테스트봇", author_id="test-author")
    response = client.post(
        "/bots",
        content=bot_request.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )
    return response.json()["bot_id"]


def _make_new_message_request(bot_id: str, text: str, reply_needed: bool) -> NewMessageRequest:
    from naraninyeo.infrastructure.util.nanoid_generator import NanoidGenerator

    return NewMessageRequest(
        bot_id=bot_id,
        message=Message(
            message_id=NanoidGenerator().generate_id(),
            channel=Channel(channel_id="test-channel", channel_name="테스트채널"),
            author=Author(author_id="test-user", author_name="테스터"),
            content=MessageContent(text=text),
            timestamp=datetime.now(UTC),
        ),
        reply_needed=reply_needed,
    )
