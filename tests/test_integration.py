from dishka import Container
import pytest
from datetime import datetime
import uuid

from naraninyeo.models.message import Message, Channel, Author, MessageContent
from naraninyeo.services.conversation_service import ConversationService

@pytest.mark.asyncio
async def test_conversation_service_responds(test_container: Container):
    """
    ConversationService가 메시지를 처리하고 응답을 생성하는지 테스트
    """
    message = Message(
        message_id=str(uuid.uuid4()),
        channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
        author=Author(author_id="test-user", author_name="Test User"),
        content=MessageContent(text="/내일 날씨 알려줘"),
        timestamp=datetime.now()
    )
    replies = []

    conversation_service: ConversationService = await test_container.get(ConversationService)

    async for reply in conversation_service.process_message(message):
        replies.append(reply)
    assert len(replies) > 0, "응답이 생성되지 않았습니다."
