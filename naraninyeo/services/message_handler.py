import traceback
from typing import AsyncIterator
from datetime import datetime

from naraninyeo.models.message import Message, MessageContent
from naraninyeo.services.message_parser import parse_message
from naraninyeo.services.api_client import send_response
from naraninyeo.services.llm_agent import generate_llm_response, should_respond, bot_author
from naraninyeo.services.random_responder import get_random_response, should_get_random_response

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
            try:
                async for event in generate_llm_response(request):
                    i += 1
                    response_text = event["response"].strip()
                    
                    if not event["is_final"]:
                        response_text = response_text + " (...)"
                    
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
                reply_message = Message(
                    message_id = f"{request.message_id}-reply-{i+1}",
                    channel=request.channel,
                    author=bot_author,
                    content=MessageContent(text=await get_random_response(request)),
                    timestamp=datetime.now()
                )
                await reply_message.save()
                yield reply_message

    except Exception as e:
        traceback.print_exc()