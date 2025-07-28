from datetime import datetime, timezone
import hashlib

from qdrant_client import models as qmodels
from opentelemetry import trace

from naraninyeo.models.message import Message
from naraninyeo.core.database import mc
from naraninyeo.core.vectorstore import vc

tracer = trace.get_tracer(__name__)

def str_to_64bit(s: str) -> int:
    """
    문자열을 64비트 해시로 변환합니다.
    """
    return int(hashlib.sha256(s.encode('utf-8')).hexdigest()[:16], 16)

@tracer.start_as_current_span("get_history")
async def get_history(room:str, timestamp: datetime, limit: int = 10, before: bool = True) -> list[Message]:
    """
    주어진 timestamp를 기준으로 메시지를 limit개만큼 가져옵니다.
    before=True이면 이전 메시지를, False이면 이후 메시지를 가져옵니다.
    """
    
    if before:
        # timestamp보다 작은 메시지들을 시간순으로 가져오기
        messages = await mc.db["messages"].find(
            {"channel.channel_id": room, "timestamp": {"$lt": timestamp}}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        messages.reverse()
    else:
        # timestamp보다 큰 메시지들을 시간순으로 가져오기
        messages = await mc.db["messages"].find(
            {"channel.channel_id": room, "timestamp": {"$gt": timestamp}}
        ).sort("timestamp", 1).limit(limit).to_list(length=limit)
    
    return [Message.model_validate(message) for message in messages]

@tracer.start_as_current_span("save_message")
async def save_message(message: Message, embeddings: list[float]):
    """
    메시지를 데이터베이스에 저장합니다.
    embeddings는 서비스 계층에서 전달받습니다.
    """
    await mc.db["messages"].update_one(
        {"message_id": message.message_id},
        {"$set": message.model_dump(by_alias=True)},
        upsert=True
    )
    await vc.upsert(
        collection_name="naraninyeo-messages",
        points=[
            qmodels.PointStruct(
                id=str_to_64bit(message.message_id),
                vector=embeddings,
                payload={
                    "message_id": message.message_id,
                    "channel_id": message.channel.channel_id,
                    "text": message.content.text
                }
            )
        ],
        wait=True
    )

@tracer.start_as_current_span("search_similar_message_ids")
async def search_similar_message_ids(channel_id: str, embeddings: list[float]) -> list[str]:
    """
    주어진 채널에서 주어진 임베딩과 유사한 메시지 ID들을 검색합니다.
    embeddings는 서비스 계층에서 전달받습니다.
    """
    search_result = await vc.search(
        collection_name="naraninyeo-messages",
        query_vector=embeddings,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="channel_id",
                    match=qmodels.MatchValue(value=channel_id)
                )
            ]
        ),
        limit=10
    )
    
    return [point.payload["message_id"] for point in search_result]

@tracer.start_as_current_span("get_messages_by_ids")
async def get_messages_by_ids(message_ids: list[str]) -> list[Message]:
    """
    메시지 ID 목록으로부터 메시지 객체들을 가져옵니다.
    """
    messages_cursor = mc.db["messages"].find(
        {"message_id": {"$in": message_ids}}
    )
    messages_list = await messages_cursor.to_list(length=len(message_ids))
    
    # 원래 순서를 유지하기 위해 dict에 저장
    messages_map = {msg["message_id"]: Message.model_validate(msg) for msg in messages_list}
    
    # 원래 검색 결과 순서대로 Message 객체 리스트 생성
    return [messages_map[msg_id] for msg_id in message_ids if msg_id in messages_map]
