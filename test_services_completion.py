#!/usr/bin/env python3
"""
완성된 서비스들 테스트
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

async def test_conversation_service():
    """ConversationService 완성 테스트"""
    print("🗣️ Testing ConversationService...")
    
    try:
        from naraninyeo.services.conversation_service import ConversationService
        from naraninyeo.models.message import Message, Author, Channel, MessageContent
        
        # Mock 의존성들 생성
        mock_repo = AsyncMock()
        mock_embedding = AsyncMock()
        mock_llm = AsyncMock()
        
        # Mock 설정
        mock_repo.get_history.return_value = []
        mock_embedding.get_embeddings.return_value = [[0.1, 0.2, 0.3]]
        mock_repo.search_similar.return_value = []
        
        # 서비스 생성
        service = ConversationService(mock_repo, mock_embedding, mock_llm)
        
        # 테스트 메시지
        test_message = Message(
            message_id="test-123",
            channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
            author=Author(author_id="test-user", author_name="Test User"),
            content=MessageContent(text="안녕하세요"),
            timestamp=datetime.now()
        )
        
        # 1. 대화 히스토리 테스트
        history = await service.get_conversation_history("test-channel", datetime.now(), "test-123")
        print("✅ get_conversation_history OK")
        
        # 2. 참고 대화 테스트
        reference = await service.get_reference_conversations("test-channel", "안녕하세요")
        print("✅ get_reference_conversations OK")
        
        # 3. LLM 컨텍스트 준비 테스트
        context = await service.prepare_llm_context(test_message)
        assert "history" in context
        assert "reference_conversations" in context
        assert "search_results" in context
        print("✅ prepare_llm_context OK")
        
        return True
        
    except Exception as e:
        print(f"❌ ConversationService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_random_responder():
    """RandomResponderService 테스트"""
    print("\n🎲 Testing RandomResponderService...")
    
    try:
        from naraninyeo.services.random_responder import RandomResponderService
        from naraninyeo.models.message import Message, Author, Channel, MessageContent
        
        # 서비스 생성
        service = RandomResponderService()
        
        # 테스트 메시지
        test_message = Message(
            message_id="test-123",
            channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
            author=Author(author_id="test-user", author_name="Test User"),
            content=MessageContent(text="안녕하세요"),
            timestamp=datetime.now()
        )
        
        # 1. 랜덤 응답 텍스트 테스트
        response_text = service.get_random_response()
        assert response_text in RandomResponderService.RANDOM_RESPONSES
        print("✅ get_random_response OK")
        
        # 2. 랜덤 응답 메시지 생성 테스트
        responses = []
        async for response in service.generate_random_response(test_message):
            responses.append(response)
        
        assert len(responses) == 1
        assert responses[0].content.text in RandomResponderService.RANDOM_RESPONSES
        print("✅ generate_random_response OK")
        
        return True
        
    except Exception as e:
        print(f"❌ RandomResponderService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_di_container_with_all_services():
    """모든 서비스가 포함된 DI 컨테이너 테스트"""
    print("\n🏗️ Testing DI Container with all services...")
    
    try:
        from naraninyeo.container import setup_dependencies, container
        from naraninyeo.services.message_service import MessageService
        from naraninyeo.services.conversation_service import ConversationService
        from naraninyeo.services.random_responder import RandomResponderService
        
        # 의존성 설정
        setup_dependencies()
        
        # 모든 서비스 가져오기
        message_service = container.get(MessageService)
        conversation_service = container.get(ConversationService)
        random_responder = container.get(RandomResponderService)
        
        print(f"✅ MessageService: {type(message_service)}")
        print(f"✅ ConversationService: {type(conversation_service)}")
        print(f"✅ RandomResponderService: {type(random_responder)}")
        
        return True
        
    except Exception as e:
        print(f"❌ DI Container test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """모든 서비스 완성 테스트 실행"""
    print("🚀 Starting completed services tests...\n")
    
    tests = [
        test_conversation_service,
        test_random_responder,
        test_di_container_with_all_services
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
    
    print(f"\n📊 Services Completion Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All services completed successfully!")
    else:
        print("⚠️ Some services need more work.")

if __name__ == "__main__":
    asyncio.run(main())
