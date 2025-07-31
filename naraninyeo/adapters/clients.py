"""
외부 API 클라이언트들 - Infrastructure Adapters
기존 services에 있던 HTTP 클라이언트들을 여기로 이동
"""
import httpx
from typing import List
from opentelemetry import trace

from naraninyeo.core.config import settings
from naraninyeo.models.message import Message

class EmbeddingClient:
    """임베딩 생성 클라이언트 - Ollama API 사용"""
    
    def __init__(self):
        self.api_url = settings.OLLAMA_API_URL
        self.model = "hf.co/Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"
    
    @trace.get_tracer(__name__).start_as_current_span("get_embeddings")
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """텍스트 목록을 임베딩으로 변환"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=20
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embeddings", [])

class LLMClient:
    """LLM 클라이언트 - agent.py 로직 통합"""
    
    def __init__(self):
        # agent.py에서 에이전트들을 import
        from naraninyeo.llm.agent import planner_agent, responder_agent
        self.planner_agent = planner_agent
        self.responder_agent = responder_agent
    
    async def should_respond(self, message: Message) -> bool:
        """메시지가 응답이 필요한지 확인 - agent.py의 로직 사용"""
        from naraninyeo.llm.agent import should_respond
        return await should_respond(message)
    
    async def generate_response(self, message: Message, history: str, similar_messages):
        """LLM 응답 생성 - agent.py의 로직 사용"""
        from naraninyeo.llm.agent import generate_llm_response
        
        # 기존 agent.py의 generate_llm_response 호출
        # 일단 빈 검색 결과로 호출 (나중에 search_results 통합)
        async for response_data in generate_llm_response(
            message, 
            history or "",  # conversation_history
            "참고할만한 예전 대화 기록이 없습니다.",  # reference_conversations
            []  # search_results - 임시로 빈 리스트
        ):
            # TeamResponse에서 텍스트만 추출
            yield response_data.get("response", "")
    
    async def create_search_plan(self, message: Message, history: str, reference_conversations: str):
        """검색 계획 생성 - agent.py의 로직 사용"""
        from naraninyeo.llm.agent import create_search_plan
        return await create_search_plan(message, history, reference_conversations)

class APIClient:
    """외부 API 통신 클라이언트"""
    
    @trace.get_tracer(__name__).start_as_current_span("send_response")
    async def send_response(self, message: Message):
        """응답 메시지 전송"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.NARANINYEO_API_URL}/reply",
                json={
                    "type": "text",
                    "room": message.channel.channel_id,
                    "data": message.content.text
                }
            )
            response.raise_for_status()
