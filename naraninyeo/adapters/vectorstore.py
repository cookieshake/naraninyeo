"""
Vector Store 연결 관리 - Infrastructure Adapter
기존 core/vectorstore.py를 이동하고 약간 개선
"""
from qdrant_client import AsyncQdrantClient
from naraninyeo.core.config import Settings

class VectorStoreAdapter:
    """Qdrant 벡터 저장소 연결 관리"""

    def __init__(self, settings: Settings):
        self.client = AsyncQdrantClient(url=settings.QDRANT_URL)
    
    async def upsert(self, collection_name: str, points):
        """벡터 데이터 삽입/업데이트"""
        return await self.client.upsert(collection_name=collection_name, points=points)
    
    async def search(self, collection_name: str, query_vector, query_filter=None, limit: int = 5):
        """벡터 유사도 검색"""
        return await self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit
        )
