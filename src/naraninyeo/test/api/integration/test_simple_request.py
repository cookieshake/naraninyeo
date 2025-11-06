from datetime import UTC, datetime

import pytest  # noqa: F401
from fastapi.testclient import TestClient

from naraninyeo.api.routers.bot import CreateBotRequest
from naraninyeo.api.routers.message import NewMessageRequest
from naraninyeo.core.models import Attachment, Author, Channel, Message, MessageContent


async def test_simple_request(test_client: TestClient) -> None:
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.text == "Naraninyeo API is running."


async def test_create_bot_simple(test_client: TestClient) -> None:
    bot = CreateBotRequest(name="Test Bot", author_id="user_123")

    response = test_client.post("/bots", content=bot.model_dump_json())
    if response.status_code != 200:
        raise AssertionError(f"Unexpected status code: {response.status_code}, response: {response.text}")
    response_json = response.json()
    assert response_json["bot_name"] == "Test Bot"

    bots = test_client.get("/bots").json()
    assert any(b["bot_name"] == "Test Bot" for b in bots)
    assert any(b["author_id"] == "user_123" for b in bots)


async def test_new_message_simple(test_client: TestClient) -> None:
    bot_id = test_client.get("/bots").json()[0]["bot_id"]
    new_message_payload = NewMessageRequest(
        bot_id=bot_id,
        message=Message(
            message_id="msg_001",
            channel=Channel(channel_id="channel_123", channel_name="text"),
            author=Author(author_id="user_456", author_name="Test User"),
            content=MessageContent(
                text="Hello, this is a test message.",
                attachments=[
                    Attachment(attachment_id="att_789", attachment_type="image", url="http://example.com/image.png")
                ],
            ),
            timestamp=datetime.now(UTC),
        ),
        reply_needed=False,
    )

    response = test_client.post("/new_message", content=new_message_payload.model_dump_json())
    if response.status_code != 200:
        raise AssertionError(f"Unexpected status code: {response.status_code}, response: {response.text}")
    response_json = response.json()
    assert response_json["is_final"] is True
    assert response_json.get("error") is None
    assert response_json.get("generated_message") is None


async def test_generate_message_simple(test_client: TestClient) -> None:
    bot_id = test_client.get("/bots").json()[0]["bot_id"]
    new_message_payload = NewMessageRequest(
        bot_id=bot_id,
        message=Message(
            message_id="msg_002",
            channel=Channel(channel_id="channel_123", channel_name="text"),
            author=Author(author_id="user_456", author_name="Test User"),
            content=MessageContent(
                text="Hello? Can you generate a response?",
                attachments=[],
            ),
            timestamp=datetime.now(UTC),
        ),
        reply_needed=True,
    )

    response = test_client.post("/new_message", content=new_message_payload.model_dump_json())
    if response.status_code != 200:
        raise AssertionError(f"Unexpected status code: {response.status_code}, response: {response.text}")
