#!/usr/bin/env python3
"""
LLM 통합 테스트
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

async def test_llm_integration():
    """LLM 통합 테스트"""
    print("🤖 Testing LLM integration...")
    
    try:
        from naraninyeo.adapters.clients import LLMClient
        from naraninyeo.models.message import Message, Author, Channel, MessageContent
        
        # LLMClient 인스턴스 생성
        llm_client = LLMClient()
        
        # 테스트 메시지 생성
        test_message = Message(
            message_id="test-123",
            channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
            author=Author(author_id="test-user", author_name="Test User"),
            content=MessageContent(text="/안녕하세요"),
            timestamp=datetime.now()
        )
        
        # 1. should_respond 테스트
        should_respond = await llm_client.should_respond(test_message)
        print(f"✅ Should respond: {should_respond}")
        
        # 2. 간단한 응답 생성 테스트 (실제 LLM 호출은 안 함)
        print("✅ LLM client instantiation OK")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_message_service_with_llm():
    """MessageService와 LLM 통합 테스트"""
    print("\n🧪 Testing MessageService with LLM integration...")
    
    try:
        from naraninyeo.services.message_service import MessageService
        from naraninyeo.models.message import Message, Author, Channel, MessageContent
        from naraninyeo.adapters.clients import LLMClient, EmbeddingClient
        from naraninyeo.adapters.repositories import MessageRepository
        
        # Mock 의존성들 생성
        mock_repo = AsyncMock()
        mock_embedding = AsyncMock()
        
        # 실제 LLMClient 사용 (하지만 실제 호출은 피함)
        llm_client = LLMClient()
        
        # Mock 설정
        mock_embedding.get_embeddings.return_value = [[0.1, 0.2, 0.3]]
        mock_repo.save.return_value = None
        mock_repo.get_history.return_value = []
        mock_repo.search_similar.return_value = []
        
        # 서비스 생성
        service = MessageService(mock_repo, llm_client, mock_embedding)
        
        # 테스트 메시지 생성 
        test_message = Message(
            message_id="test-123",
            channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
            author=Author(author_id="test-user", author_name="Test User"),
            content=MessageContent(text="/안녕하세요"),
            timestamp=datetime.now()
        )
        
        # should_respond_to 테스트
        should_respond = await service.should_respond_to(test_message)
        print(f"✅ MessageService should_respond_to: {should_respond}")
        
        print("✅ MessageService with LLM integration structure OK")
        
        return True
        
    except Exception as e:
        print(f"❌ MessageService with LLM test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """LLM 통합 테스트 실행"""
    print("🚀 Starting LLM integration tests...\n")
    
    tests = [
        test_llm_integration,
        test_message_service_with_llm
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
    
    print(f"\n📊 LLM Integration Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 LLM integration successful!")
    else:
        print("⚠️ Some LLM integration tests failed.")

if __name__ == "__main__":
    asyncio.run(main())
