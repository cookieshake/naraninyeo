"""
Repository 구현체들을 한 파일에 모아서 관리
파일 수를 늘리지 않으면서도 책임은 분리
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional
import hashlib

from qdrant_client import models as qmodels
from opentelemetry import trace

from naraninyeo.models.message import Message
from naraninyeo.adapters.database import database_adapter
from naraninyeo.adapters.vectorstore import vector_store_adapter

tracer = trace.get_tracer(__name__)

class MessageRepository:
    """MongoDB + Qdrant를 사용한 메시지 저장소"""
    
    def str_to_64bit(self, s: str) -> int:
        return int(hashlib.sha256(s.encode('utf-8')).hexdigest()[:16], 16)
    
    @tracer.start_as_current_span("save_message")
    async def save(self, message: Message, embedding: List[float]) -> None:
        # MongoDB에 메시지 저장
        message_dict = {
            "message_id": message.message_id,
            "channel": {
                "channel_id": message.channel.channel_id,
                "channel_name": message.channel.channel_name,
            },
            "author": {
                "author_id": message.author.author_id,
                "author_name": message.author.author_name,
            },
            "content": {
                "text": message.content.text,
                "attachments": [att.model_dump() for att in message.content.attachments],
            },
            "timestamp": message.timestamp,
        }
        await database_adapter.db["messages"].insert_one(message_dict)
        
        # Qdrant에 벡터 저장
        point = qmodels.PointStruct(
            id=self.str_to_64bit(message.message_id),
            vector=embedding,
            payload={
                "message_id": message.message_id,
                "room": message.channel.channel_id,
                "text": message.content.text,
                "timestamp": message.timestamp.isoformat(),
                "author": message.author.author_name,
            }
        )
        await vector_store_adapter.upsert(collection_name="naraninyeo-messages", points=[point])

    @tracer.start_as_current_span("get_history")
    async def get_history(self, room: str, timestamp: datetime, limit: int = 10, before: bool = True) -> List[Message]:
        if before:
            messages = await database_adapter.db["messages"].find(
                {"channel.channel_id": room, "timestamp": {"$lt": timestamp}}
            ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        else:
            messages = await database_adapter.db["messages"].find(
                {"channel.channel_id": room, "timestamp": {"$gt": timestamp}}
            ).sort("timestamp", 1).limit(limit).to_list(length=limit)
        
        return [self._dict_to_message(msg) for msg in messages]
    
    @tracer.start_as_current_span("search_similar")
    async def search_similar(self, embedding: List[float], room: str, limit: int = 5) -> List[Message]:
        search_result = await vector_store_adapter.search(
            collection_name="naraninyeo-messages",
            query_vector=embedding,
            query_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="room", match=qmodels.MatchValue(value=room))]
            ),
            limit=limit,
        )
        
        message_ids = [hit.payload["message_id"] for hit in search_result]
        messages = await database_adapter.db["messages"].find(
            {"message_id": {"$in": message_ids}}
        ).to_list(length=limit)
        
        return [self._dict_to_message(msg) for msg in messages]
    
    def _dict_to_message(self, msg_dict: dict) -> Message:
        """MongoDB 문서를 Message 객체로 변환"""
        from naraninyeo.models.message import Author, Channel, MessageContent, Attachment
        
        return Message(
            message_id=msg_dict["message_id"],
            channel=Channel(**msg_dict["channel"]),
            author=Author(**msg_dict["author"]),
            content=MessageContent(
                text=msg_dict["content"]["text"],
                attachments=[Attachment(**att) for att in msg_dict["content"]["attachments"]]
            ),
            timestamp=msg_dict["timestamp"]
        )

# ==================== 기타 Infrastructure ====================
class LLMClient:
    """LLM 클라이언트 - 기존 llm/agent.py 래핑"""
    pass

class VectorStore:
    """벡터 저장소 - 임베딩 관련 로직"""
    pass
