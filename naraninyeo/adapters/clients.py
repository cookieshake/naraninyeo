"""
외부 API 클라이언트들 - Infrastructure Adapters
기존 services에 있던 HTTP 클라이언트들을 여기로 이동
"""
import httpx
from typing import List
from opentelemetry import trace

from naraninyeo.adapters.agents.planner import Planner
from naraninyeo.adapters.agents.responder import Responder
from naraninyeo.core.config import Settings
from naraninyeo.models.message import Message

class EmbeddingClient:
    """임베딩 생성 클라이언트 - Ollama API 사용"""
    
    def __init__(self, settings: Settings):
        self.api_url = settings.LLAMA_CPP_MODELS_URL
        self.model = "qwen3-embedding-0-6b"
    
    @trace.get_tracer(__name__).start_as_current_span("get_embeddings")
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """텍스트 목록을 임베딩으로 변환"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/{self.model}/v1/embeddings",
                json={"model": self.model, "input": texts},
                timeout=60
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            return [item.get("embedding", []) for item in data]

class LLMClient:
    """LLM 클라이언트 - agent.py 로직 통합"""
    
    def __init__(self, planner_agent: Planner, responder: Responder):
        self.planner = planner_agent
        self.responder = responder
    
    async def generate_response(self, message: Message, history: str, reference_conversations: str, search_results: List):
        """LLM 응답 생성"""
        
        # LLM 응답 생성
        async for response_data in self.responder.generate_response(
            message, 
            history or "",  # conversation_history
            reference_conversations or "참고할만한 예전 대화 기록이 없습니다.",  # reference_conversations
            search_results or []  # search_results
        ):
            # TeamResponse에서 텍스트만 추출
            yield response_data.get("response", "")
    
    async def create_search_plan(self, message: Message, history: str, reference_conversations: str):
        """검색 계획 생성"""
        return await self.planner.create_search_plan(message, history, reference_conversations)

class APIClient:
    """외부 API 통신 클라이언트"""

    def __init__(self, settings: Settings):
        self.api_url = settings.NARANINYEO_API_URL
    
    @trace.get_tracer(__name__).start_as_current_span("send_response")
    async def send_response(self, message: Message):
        """응답 메시지 전송"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/reply",
                json={
                    "type": "text",
                    "room": message.channel.channel_id,
                    "data": message.content.text
                }
            )
            response.raise_for_status()
