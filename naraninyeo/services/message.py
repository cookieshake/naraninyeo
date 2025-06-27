from datetime import datetime
import traceback
from typing import AsyncIterator, Optional
from zoneinfo import ZoneInfo
import anyio

from naraninyeo.handlers.message import should_respond
from naraninyeo.models.message import Message, MessageContent, Author
from naraninyeo.handlers.response import generate_llm_response

bot_author = Author(
    author_id="bot-naraninyeo",
    author_name="나란잉여"
)

async def handle_message(request: Message) -> AsyncIterator[Message]:
    """
    Handle incoming messages and save them to MongoDB.
    Only respond if the message starts with '/'.
    """
    try:
        await request.save()
        needs_response = await should_respond(request)
        if needs_response:
            i = 0
            async for event in generate_llm_response(request):
                i += 1
                response_text = event["response"].strip()
                
                # 중간 과정 메시지 필터링
                if any(keyword in response_text.lower() for keyword in [
                    "검색 중", "분석 중", "열심히", "곧", "기다려", "찾고 있어",
                    "searching", "analyzing", "wait", "soon", "looking for"
                ]):
                    continue
                
                # 너무 짧거나 의미 없는 메시지 필터링
                if len(response_text) < 10:
                    continue
                
                if not event["is_final"]:
                    response_text = response_text + " (더 있음)"
                
                reply_message = Message(
                    message_id=f"{request.message_id}-reply-{i}",
                    channel=request.channel,
                    author=bot_author,
                    content=MessageContent(text=response_text),
                    timestamp=datetime.now()
                )
                await reply_message.save()
                yield reply_message
    except Exception as e:
        traceback.print_exc()
