import traceback
from typing import AsyncIterator
from datetime import datetime

from naraninyeo.models.message import Message, MessageContent
from naraninyeo.llm import should_respond
from naraninyeo.llm.agent import bot_author, generate_llm_response
from naraninyeo.services.random_responder import get_random_response
from naraninyeo.services.message_service import save_message
from naraninyeo.services.conversation_service import prepare_llm_context

async def handle_message(request: Message) -> AsyncIterator[Message]:
    """
    Handle incoming messages and save them to MongoDB.
    Only respond if the message starts with '/'.
    """
    try:
        await save_message(request)
        needs_response = await should_respond(request)
        if needs_response:
            i = 0
            try:
                # LLM 응답 생성에 필요한 모든 컨텍스트 준비
                context = await prepare_llm_context(request)
                
                # LLM 응답 생성
                async for event in generate_llm_response(
                    request, 
                    context["history"],
                    context["reference_conversations"],
                    context["search_results"]
                ):
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
                    await save_message(reply_message)
                    yield reply_message
            except Exception as e:
                reply_message = Message(
                    message_id = f"{request.message_id}-reply-{i+1}",
                    channel=request.channel,
                    author=bot_author,
                    content=MessageContent(text=await get_random_response(request)),
                    timestamp=datetime.now()
                )
                await save_message(reply_message)
                yield reply_message

    except Exception as e:
        traceback.print_exc()