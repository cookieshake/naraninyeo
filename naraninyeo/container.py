# 간단한 DI 컨테이너 - 파일 하나로 해결
from typing import Dict, Any, TypeVar, Type
from dataclasses import dataclass

T = TypeVar('T')

@dataclass
class Container:
    """초간단 DI 컨테이너 - 별도 라이브러리 없이"""
    _instances: Dict[Type, Any] = None
    
    def __post_init__(self):
        if self._instances is None:
            self._instances = {}
    
    def register(self, interface: Type[T], implementation: T):
        self._instances[interface] = implementation
    
    def get(self, interface: Type[T]) -> T:
        return self._instances[interface]

# 전역 컨테이너
container = Container()

# 초기화 함수 - 애플리케이션 시작시 한번만 호출
def setup_dependencies():
    from naraninyeo.adapters.repositories import MessageRepository
    from naraninyeo.adapters.clients import LLMClient, EmbeddingClient, APIClient
    from naraninyeo.services.message_service import MessageService
    from naraninyeo.services.conversation_service import ConversationService
    from naraninyeo.services.random_responder import RandomResponderService
    
    # Infrastructure 등록
    message_repo = MessageRepository()
    llm_client = LLMClient()
    embedding_client = EmbeddingClient()
    api_client = APIClient()
    
    # Services 등록  
    message_service = MessageService(message_repo, llm_client, embedding_client)
    conversation_service = ConversationService(message_repo, embedding_client, llm_client)
    random_responder = RandomResponderService()
    
    container.register(MessageRepository, message_repo)
    container.register(LLMClient, llm_client)
    container.register(EmbeddingClient, embedding_client)
    container.register(APIClient, api_client)
    container.register(MessageService, message_service)
    container.register(ConversationService, conversation_service)
    container.register(RandomResponderService, random_responder)
