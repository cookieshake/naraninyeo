import logging
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from dishka import AsyncContainer

from naraninyeo.domain.application.new_message_handler import NewMessageHandler
from naraninyeo.domain.model.message import Author, Channel, Message, MessageContent

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="module")
async def message_handler(test_container: AsyncContainer) -> NewMessageHandler:
    return await test_container.get(NewMessageHandler)


async def test_handle_new_message(caplog: pytest.LogCaptureFixture, message_handler: NewMessageHandler):
    new_message = Message(
        message_id=str(uuid.uuid4()),
        channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
        author=Author(author_id="test-user", author_name="Test User"),
        content=MessageContent(text="/내일 날씨 알려줘"),
        timestamp=datetime.now(),
    )
    replies = []
    async for reply in message_handler.handle(new_message):
        replies.append(reply)
    logger.info(f"Replies generated: {len(replies)}")
    assert len(replies) > 0, "Expected at least one reply"
