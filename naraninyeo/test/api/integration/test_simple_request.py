
from datetime import UTC, datetime

from dishka import AsyncContainer
from fastapi.testclient import TestClient

from naraninyeo.api.routers.message import NewMessageRequest
from naraninyeo.core.models import Author, Channel, Message, MessageContent


def test_simple_request(test_client: TestClient) -> None:
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.text == "Naraninyeo API is running."

def test_new_message_simple(test_client: TestClient) -> None:
    new_message_payload = NewMessageRequest(
        bot_id="bot_123",
        message=Message(
            message_id="msg_001",
            channel=Channel(channel_id="channel_123", channel_name="text"),
            author=Author(author_id="user_456", author_name="Test User"),
            content=MessageContent(text="Hello, this is a test message."),
            timestamp=datetime.now(UTC),
        ),
        reply_needed=False
    )

    response = test_client.post("/new_message", content=new_message_payload.model_dump_json())
    assert response.text is None
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["is_final"] is True
    assert response_json.get("error") is None
    assert response_json.get("generated_message") is None
