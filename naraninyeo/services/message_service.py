"""메시지 관련 비즈니스 로직"""

from naraninyeo.models.message import Message
from naraninyeo.services.embedding_service import get_embeddings
from naraninyeo.repository.message import (
    save_message as save_message_repo,
    search_similar_message_ids,
    get_messages_by_ids,
    get_history
)

async def save_message(message: Message):
    """메시지를 저장합니다."""
    embeddings = await get_embeddings([message.content.text])
    await save_message_repo(message, embeddings[0])

async def search_similar_messages(channel_id: str, text: str) -> list[list[Message]]:
    """
    주어진 채널에서 주어진 텍스트와 유사한 메시지를 검색하고,
    관련 대화 클러스터를 만들어 반환합니다.
    """
    embeddings = await get_embeddings([text])
    similar_message_ids = await search_similar_message_ids(channel_id, embeddings[0])
    ordered_similar_messages = await get_messages_by_ids(similar_message_ids)

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
