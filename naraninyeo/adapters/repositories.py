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
import httpx

from naraninyeo.adapters.database import DatabaseAdapter
from naraninyeo.models.message import Message, Attachment
from naraninyeo.adapters.vectorstore import VectorStoreAdapter


class MessageRepository:
    """MongoDB + Qdrant를 사용한 메시지 저장소"""
    
    def __init__(self, database_adapter: DatabaseAdapter, vector_store_adapter: VectorStoreAdapter):
        self.database_adapter = database_adapter
        self.vector_store_adapter = vector_store_adapter
        
    def str_to_64bit(self, s: str) -> int:
        return int(hashlib.sha256(s.encode('utf-8')).hexdigest()[:16], 16)
    
    @trace.get_tracer(__name__).start_as_current_span("save_message")
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
        await self.database_adapter.db["messages"].insert_one(message_dict)
        
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
        await self.vector_store_adapter.upsert(collection_name="naraninyeo-messages", points=[point])

    @trace.get_tracer(__name__).start_as_current_span("get_history")
    async def get_history(self, room: str, timestamp: datetime, limit: int = 10, before: bool = True) -> List[Message]:
        if before:
            messages = await self.database_adapter.db["messages"].find(
                {"channel.channel_id": room, "timestamp": {"$lt": timestamp}}
            ).sort("timestamp", -1).limit(limit).to_list(length=limit)
        else:
            messages = await self.database_adapter.db["messages"].find(
                {"channel.channel_id": room, "timestamp": {"$gt": timestamp}}
            ).sort("timestamp", 1).limit(limit).to_list(length=limit)
        
        return [self._dict_to_message(msg) for msg in messages]
    
    @trace.get_tracer(__name__).start_as_current_span("search_similar")
    async def search_similar(self, embedding: List[float], room: str, limit: int = 5) -> List[Message]:
        search_result = await self.vector_store_adapter.search(
            collection_name="naraninyeo-messages",
            query_vector=embedding,
            query_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="room", match=qmodels.MatchValue(value=room))]
            ),
            limit=limit,
        )
        
        message_ids = [hit.payload["message_id"] for hit in search_result]
        messages = await self.database_adapter.db["messages"].find(
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

class AttachmentRepository:
    """첨부파일 저장소"""
    
    def __init__(self, database_adapter: DatabaseAdapter):
        self.database_adapter = database_adapter
    
    @trace.get_tracer(__name__).start_as_current_span("create_attachment_with_content_url")
    async def create_with_content_url(
        self,
        attachment_id: str,
        attachment_type: str,
        content_url: str
    ) -> Attachment:
        """URL에서 첨부파일을 생성합니다."""
        async with httpx.AsyncClient() as client:
            response = await client.get(content_url)
            attachment = Attachment(
                attachment_id=attachment_id,
                attachment_type=attachment_type,
                content_type=response.headers.get("Content-Type"),
                content_length=response.headers.get("Content-Length")
            )
            await self.save_content(attachment_id, response.content)
            return attachment

    @trace.get_tracer(__name__).start_as_current_span("save_attachment_content")
    async def save_content(self, attachment_id: str, content: bytes):
        """첨부파일 내용을 저장합니다."""
        await self.database_adapter.db["attachment_content"].update_one(
            {"attachment_id": attachment_id},
            {"$set": {"content": content}},
            upsert=True
        )

    @trace.get_tracer(__name__).start_as_current_span("get_attachment_content")
    async def get_content(self, attachment_id: str) -> bytes:
        """첨부파일 내용을 가져옵니다."""
        result = await self.database_adapter.db["attachment_content"].find_one({"attachment_id": attachment_id})
        return result["content"] if result else None
