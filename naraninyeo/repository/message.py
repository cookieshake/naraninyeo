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

async def search_similar_messages(channel_id: str, text: str) -> list[list[Message]]:
    """
    주어진 채널에서 주어진 텍스트와 유사한 메시지를 검색하고,
    관련 대화 클러스터를 만들어 반환합니다.
    """
    embeddings = await get_embeddings([text])
    search_result = await vc.search(
        collection_name="naraninyeo-messages",
        query_vector=embeddings[0],
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
    
    similar_message_ids = [point.payload["message_id"] for point in search_result]
    
    # MongoDB에서 메시지 상세 정보 가져오기
    similar_messages_cursor = mc.db["messages"].find(
        {"message_id": {"$in": similar_message_ids}}
    )
    similar_messages_list = await similar_messages_cursor.to_list(length=10)
    
    # 원래 순서를 유지하기 위해 dict에 저장
    similar_messages_map = {msg["message_id"]: Message.model_validate(msg) for msg in similar_messages_list}
    
    # 원래 검색 결과 순서대로 Message 객체 리스트 생성
    ordered_similar_messages = [similar_messages_map[msg_id] for msg_id in similar_message_ids if msg_id in similar_messages_map]

    clusters = []
    for message in ordered_similar_messages:
        before_messages = await get_history(channel_id, message.timestamp, limit=5, before=True)
        after_messages = await get_history(channel_id, message.timestamp, limit=5, before=False)
        
        cluster = before_messages + [message] + after_messages
        
        # 클러스터 병합 로직
        merged = False
        for i, existing_cluster in enumerate(clusters):
            # set으로 변환하여 겹치는 메시지가 있는지 확인
            if set(m.message_id for m in existing_cluster) & set(m.message_id for m in cluster):
                # 겹치면 합집합을 구하고, timestamp 순으로 정렬
                combined_ids = {m.message_id for m in existing_cluster} | {m.message_id for m in cluster}
                
                # 두 클러스터의 모든 메시지를 합친 후 중복 제거
                combined_messages_map = {m.message_id: m for m in existing_cluster}
                combined_messages_map.update({m.message_id: m for m in cluster})
                
                # message_id를 기준으로 정렬된 메시지 리스트 생성
                sorted_messages = sorted(combined_messages_map.values(), key=lambda m: m.timestamp)
                
                clusters[i] = sorted_messages
                merged = True
                break
        
        if not merged:
            clusters.append(cluster)
        
        if len(clusters) >= 3:
            break
            
    return clusters