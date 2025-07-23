from datetime import datetime, timezone
import hashlib

from qdrant_client import models as qmodels

from naraninyeo.models.message import Message
from naraninyeo.services.embedding_service import get_embeddings
from naraninyeo.core.database import mc
from naraninyeo.core.vectorstore import vc

def str_to_64bit(s: str) -> int:
    """
    문자열을 64비트 해시로 변환합니다.
    """
    return int(hashlib.sha256(s.encode('utf-8')).hexdigest()[:16], 16)

async def get_history(room:str, timestamp: datetime, limit: int = 10) -> list[Message]:
    """
    주어진 timestamp보다 작은 메시지를 limit개만큼 가져옵니다.
    """
    
    # timestamp보다 작거나 같은 메시지들을 시간순으로 가져오기
    messages = await mc.db["messages"].find(
        {"channel.channel_id": room, "timestamp": {"$lt": timestamp}}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    messages.reverse()
    
    return [Message.model_validate(message) for message in messages]

async def save_message(message: Message):
    """
    메시지를 데이터베이스에 저장합니다.
    """
    await mc.db["messages"].update_one(
        {"message_id": message.message_id},
        {"$set": message.model_dump(by_alias=True)},
        upsert=True
    )
    embeddings = await get_embeddings([message.content.text])
    await vc.upsert(
        collection_name="naraninyeo-messages",
        points=[
            qmodels.PointStruct(
                id=str_to_64bit(message.message_id),
                vector=embeddings[0],
                payload={
                    "message_id": message.message_id,
                    "channel_id": message.channel.channel_id,
                    "text": message.content.text
                }
            )
        ],
        wait=True
    )