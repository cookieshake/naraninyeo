# naraninyeo/test_integration.py

import asyncio
import json
from datetime import datetime, timezone
import uuid
from unittest.mock import AsyncMock, patch, PropertyMock

import pytest
import pytest_asyncio
from httpx import Response

from naraninyeo.core.config import settings
from naraninyeo.core.database import mc
from naraninyeo.main import parse_message, send_response
from naraninyeo.models.message import Message, Channel, Author, MessageContent
from naraninyeo.services.message_handler import handle_message

# Override settings for testing
TEST_DB_NAME = "naraninyeo-test"
settings.MONGODB_DB_NAME = TEST_DB_NAME
settings.NARANINYEO_API_URL = "http://test-api"

from motor.motor_asyncio import AsyncIOMotorClient

# --- Fixtures ---

@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Set up and tear down the database for each test."""
    # Create a new client and database for each test
    test_client = AsyncIOMotorClient(settings.MONGODB_URL)
    test_db = test_client[settings.MONGODB_DB_NAME]

    # Patch the global mc object's internal attributes and methods
    with patch("naraninyeo.core.database.mc._db", new=test_db), \
         patch("naraninyeo.core.database.mc.client", new=test_client), \
         patch("naraninyeo.core.database.mc.connect_to_database", new_callable=AsyncMock) as mock_connect:
        
        mock_connect.return_value = None # Ensure connect_to_database does nothing

        yield # Run the test

    # Clean up after the test
    await test_client.drop_database(settings.MONGODB_DB_NAME)
    test_client.close()


@pytest.fixture
def mock_kafka_message():
    """Provides a mock Kafka message."""
    return {
        "json": {
            "id": "test-message-id-1",
            "chat_id": "test-channel",
            "user_id": "test-user",
            "message": "/안녕",
            "type": "1",
            "attachment": "{}",
            "created_at": str(int(datetime.now(timezone.utc).timestamp()))
        },
        "sender": "테스터",
        "room": "테스트룸"
    }

# --- Tests ---

@pytest.mark.asyncio
@patch("naraninyeo.llm.agent.responder_agent.run")
async def test_full_message_flow(mock_agent_run, mock_kafka_message, httpx_mock):
    """
    Tests the full flow from parsing a message to sending a response.
    """
    # --- Arrange ---
    # Mock the LLM agent response
    mock_llm_response = AsyncMock()
    mock_llm_response.output = "안녕하세요! 반갑습니다"
    mock_agent_run.return_value = mock_llm_response

    # Mock the reply API endpoint
    httpx_mock.add_response(url=f"{settings.NARANINYEO_API_URL}/reply", method="POST", status_code=200)

    # --- Act ---
    # 1. Parse the incoming message (from main.py)
    incoming_message = await parse_message(mock_kafka_message)

    # 2. Handle the message and generate replies (from services.message.py)
    replies = []
    async for r in handle_message(incoming_message):
        replies.append(r)
        # 3. Send the response (from main.py)
        await send_response(r)

    # --- Assert ---
    # Assert a reply was generated
    assert len(replies) == 1
    reply = replies[0]
    assert reply.content.text == "안녕하세요! 반갑습니다"
    assert reply.author.author_name == "나란잉여"
    assert reply.channel.channel_id == "test-channel"

    # Assert the LLM agent was called correctly
    mock_agent_run.assert_called_once()
    call_args = mock_agent_run.call_args[0][0]
    assert "새로 들어온 메시지:" in call_args
    assert "/안녕" in call_args

    # Assert the reply API was called
    sent_requests = httpx_mock.get_requests()
    assert len(sent_requests) == 1
    sent_request_data = json.loads(sent_requests[0].content)
    assert sent_request_data["room"] == "test-channel"
    assert sent_request_data["data"] == "안녕하세요! 반갑습니다"

    # Assert messages were saved to the database
    db = mc.db
    saved_incoming_msg = await db.messages.find_one({"message_id": "test-message-id-1"})
    assert saved_incoming_msg is not None
    assert saved_incoming_msg["content"]["text"] == "/안녕"

    saved_reply_msg = await db.messages.find_one({"message_id": f"{incoming_message.message_id}-reply-1"})
    assert saved_reply_msg is not None
    assert saved_reply_msg["content"]["text"] == "안녕하세요! 반갑습니다"


@pytest.mark.asyncio
@patch("naraninyeo.models.message.httpx.AsyncClient")
async def test_image_attachment_parsing(MockAsyncClient, mock_kafka_message):
    """
    Tests that a message with an image attachment is parsed correctly.
    """
    # --- Arrange ---
    # Mock the response for fetching the attachment content
    mock_response = Response(
        200,
        headers={"Content-Type": "image/png", "Content-Length": "12345"},
        content=b"fake-image-bytes"
    )
    mock_async_client_instance = MockAsyncClient.return_value.__aenter__.return_value
    mock_async_client_instance.get.return_value = mock_response

    # Update kafka message to be an image message
    mock_kafka_message["json"]["type"] = "2"
    mock_kafka_message["json"]["message"] = "이미지"
    mock_kafka_message["json"]["attachment"] = json.dumps({"url": "http://example.com/image.png"})

    # --- Act ---
    message = await parse_message(mock_kafka_message)

    # --- Assert ---
    assert message.content.text == "이미지"
    assert len(message.content.attachments) == 1
    attachment = message.content.attachments[0]
    assert attachment.attachment_type == "image"
    assert attachment.content_type == "image/png"
    assert attachment.content_length == 12345

    # Assert that the attachment content was saved to the DB
    saved_content = await mc.db["attachment_content"].find_one({"attachment_id": attachment.attachment_id})
    assert saved_content is not None
    assert saved_content["content"] == b"fake-image-bytes"


@pytest.mark.asyncio
@patch("naraninyeo.llm.agent.responder_agent.run")
async def test_history_is_included_in_prompt(mock_agent_run):
    """
    Tests that previous messages are correctly fetched and included in the LLM prompt.
    """
    # --- Arrange ---
    channel_id = "history-test-channel"
    db = mc.db

    # Save some history messages
    history_messages_data = [
        {
            "message_id": "hist-1", "channel": {"channel_id": channel_id, "channel_name": "test"},
            "author": {"author_id": "user1", "author_name": "유저1"}, "content": {"text": "첫번째 메시지"},
            "timestamp": datetime(2025, 7, 20, 10, 0, 0)
        },
        {
            "message_id": "hist-2", "channel": {"channel_id": channel_id, "channel_name": "test"},
            "author": {"author_id": "user2", "author_name": "유저2"}, "content": {"text": "두번째 메시지"},
            "timestamp": datetime(2025, 7, 20, 10, 1, 0)
        }
    ]
    await db.messages.insert_many(history_messages_data)

    # Mock the LLM agent response
    mock_llm_response = AsyncMock()
    mock_llm_response.output = "History received."
    mock_agent_run.return_value = mock_llm_response

    # Create the new incoming message
    new_message = Message(
        message_id="new-msg-1",
        channel=Channel(channel_id=channel_id, channel_name="test"),
        author=Author(author_id="user1", author_name="유저1"),
        content=MessageContent(text="/이어지는 질문"),
        timestamp=datetime(2025, 7, 20, 10, 2, 0)
    )

    # --- Act ---
    async for _ in handle_message(new_message):
        pass

    # --- Assert ---
    mock_agent_run.assert_called_once()
    call_args = mock_agent_run.call_args[0][0]

    # Check that the history is in the prompt
    assert "이전 대화 기록:" in call_args
    assert "유저1 : 첫번째 메시지" in call_args
    assert "유저2 : 두번째 메시지" in call_args
    assert "새로 들어온 메시지:" in call_args
    assert "유저1 : /이어지는 질문" in call_args