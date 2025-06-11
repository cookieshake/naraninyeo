import random

from naraninyeo.models.message import MessageRequest
from naraninyeo.core.database import db
from naraninyeo.handlers.response import generate_llm_response, get_random_response

async def save_message(request: MessageRequest, response: str | None = None):
    """
    메시지를 MongoDB에 저장합니다.
    """
    message_data = {
        "content": request.content,
        "response": response,
        "timestamp": request.timestamp
    }
    await db.messages.insert_one(message_data)

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
        print(e)
    return get_random_response(request.content)
    