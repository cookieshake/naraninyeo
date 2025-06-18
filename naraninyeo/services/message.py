import random
import traceback

from naraninyeo.models.message import MessageRequest, MessageDocument
from naraninyeo.core.database import db
from naraninyeo.handlers.response import generate_llm_response, get_random_response

def save_message(doc: MessageDocument):
    """
    메시지를 MongoDB에 저장합니다.
    """
    # Use upsert to handle duplicates
    db.get_db.messages.update_one(
        {"_id": doc.message_id},
        {"$set": doc.model_dump(by_alias=True)},
        upsert=True
    ) 


def should_respond(request: MessageDocument) -> bool:
    """
    메시지가 응답이 필요한지 확인합니다.
    """
    return request.content.startswith('/')

def get_response(request: MessageDocument) -> str:
    """
    LLM을 사용하여 응답을 생성합니다.
    """
    try:
        return generate_llm_response(request) 
    except Exception as e:
        traceback.print_exc()
    return get_random_response(request)
