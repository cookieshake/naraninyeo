import random
import traceback

from naraninyeo.models.message import MessageRequest, MessageDocument
from naraninyeo.core.database import db
from naraninyeo.handlers.response import generate_llm_response, get_random_response

async def save_message(request: MessageRequest, response: str | None = None):
    """
    메시지를 MongoDB에 저장합니다.
    """
    message_doc = MessageDocument(
        _id=request.logId,
        room=request.room,
        channel_id=request.channelId,
        author_name=request.author.name,
        content=request.content,
        has_response=response is not None,
        response_content=response
    )
    
    # Use upsert to handle duplicates
    await db.get_db.messages.update_one(
        {"_id": message_doc.message_id},
        {"$set": message_doc.model_dump(by_alias=True)},
        upsert=True
    ) 


async def should_respond(request: MessageRequest) -> bool:
    """
    메시지가 응답이 필요한지 확인합니다.
    """
    return request.content.startswith('/')

async def get_response(request: MessageRequest) -> str:
    """
    LLM을 사용하여 응답을 생성합니다.
    """
    try:
        if random.random() < 0.5:
            return await generate_llm_response(request.content) 
    except Exception as e:
        traceback.print_exc()
    return get_random_response(request.content)
    