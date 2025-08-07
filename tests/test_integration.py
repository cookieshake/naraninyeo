import pytest
import asyncio
from datetime import datetime
import uuid

from naraninyeo.di import container
from naraninyeo.services.conversation_service import ConversationService
from naraninyeo.models.message import Message, Channel, Author, MessageContent

@pytest.fixture(scope="module")
async def conversation_service():
    """Provides a ConversationService instance for tests."""
    # This fixture will run once per module
    service = await container.get(ConversationService)
    yield service
    # Teardown: close the container after all tests in the module have run
    await container.close()

@pytest.mark.asyncio
async def test_conversation_service_responds(conversation_service: ConversationService):
    """
    Tests that the conversation service can process a message and generate a reply.
    This test mimics the core logic of the cli_client.
    """
    # 1. Create a test message that should trigger a response
    message = Message(
        message_id=str(uuid.uuid4()),
        channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
        author=Author(author_id="test-user", author_name="Test User"),
        content=MessageContent(text="/hello"),  # Using '/' to trigger the bot
        timestamp=datetime.now()
    )

    # 2. Process the message
    replies = []
    async for reply in conversation_service.process_message(message):
        replies.append(reply)

    # 3. Assert that we got at least one reply
    assert len(replies) > 0

    # 4. Assert that the reply has content
    reply = replies[0]
    assert reply is not None
    assert isinstance(reply, Message)
    assert reply.content.text is not None
    assert len(reply.content.text) > 0
    print(f"Received reply: {reply.content.text}")
