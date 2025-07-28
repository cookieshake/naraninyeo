"""LLM 관련 인터페이스 정의"""

from abc import ABC, abstractmethod
from typing import List
from naraninyeo.models.message import Message

class MessageRepositoryInterface(ABC):
    """메시지 저장소 인터페이스"""
    
    @abstractmethod
    async def get_history(self, channel_id: str, timestamp: int, limit: int) -> List[Message]:
        pass
    
    @abstractmethod
    async def search_similar_messages(self, channel_id: str, query: str) -> List[List[Message]]:
        pass

class SearchServiceInterface(ABC):
    """검색 서비스 인터페이스"""
    
    @abstractmethod
    async def search_news(self, query: str, limit: int, sort: str = "sim"):
        pass
    
    @abstractmethod
    async def search_blog(self, query: str, limit: int, sort: str = "sim"):
        pass
    
    @abstractmethod
    async def search_web(self, query: str, limit: int, sort: str = "sim"):
        pass
    
    @abstractmethod
    async def search_encyclopedia(self, query: str, limit: int, sort: str = "sim"):
        pass
    
    @abstractmethod
    async def search_cafe(self, query: str, limit: int, sort: str = "sim"):
        pass
    
    @abstractmethod
    async def search_doc(self, query: str, limit: int, sort: str = "sim"):
        pass
