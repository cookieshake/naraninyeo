
import traceback
from typing import Optional
import anyio

from naraninyeo.handlers.message import should_respond
from naraninyeo.models.message import Message, MessageContent, Author
from naraninyeo.handlers.response import generate_llm_response

bot_author = Author(
    author_id="bot-naraninyeo",
    author_name="나란잉여"
)

async def handle_message(request: Message) -> Optional[Message]:
    """
    Handle incoming messages and save them to MongoDB.
    Only respond if the message starts with '/'.
    """
    try:
        await request.save()
        needs_response = await should_respond(request)
        if needs_response:
            response_message = await generate_llm_response(request)
            reply_message = Message(
                message_id=f"{request.message_id}-reply",
                channel=request.channel,
                author=bot_author,
                content=MessageContent(text=response_message),
                timestamp=request.timestamp
            )
            await reply_message.save()
            return reply_message
        else:
            return None
    except Exception as e:
        traceback.print_exc()
        return None
