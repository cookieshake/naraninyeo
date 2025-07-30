#!/usr/bin/env python3
"""
리팩토링된 코드 구조 테스트
"""

def test_imports():
    """import 테스트"""
    print("🧪 Testing imports...")
    
    try:
        from naraninyeo.adapters.clients import EmbeddingClient, LLMClient, APIClient
        print("✅ Clients import OK")
    except Exception as e:
        print(f"❌ Clients import failed: {e}")
        return False
    
    try:
        from naraninyeo.adapters.repositories import MessageRepository
        print("✅ Repository import OK")
    except Exception as e:
        print(f"❌ Repository import failed: {e}")
        return False
    
    try:
        from naraninyeo.services.message_service import MessageService
        print("✅ MessageService import OK")
    except Exception as e:
        print(f"❌ MessageService import failed: {e}")
        return False
    
    return True

def test_di_container():
    """DI 컨테이너 테스트 (데이터베이스 연결 없이)"""
    print("\n🧪 Testing DI Container...")
    
    try:
        from naraninyeo.container import Container
        
        # 간단한 컨테이너 테스트
        container = Container()
        
        class MockService:
            def __init__(self):
                self.name = "mock"
        
        mock_service = MockService()
        container.register(MockService, mock_service)
        
        retrieved = container.get(MockService)
        assert retrieved.name == "mock"
        print("✅ DI Container basic functionality OK")
        return True
        
    except Exception as e:
        print(f"❌ DI Container test failed: {e}")
        return False

def test_message_creation():
    """메시지 모델 생성 테스트"""
    print("\n🧪 Testing Message model...")
    
    try:
        from naraninyeo.models.message import Message, Author, Channel, MessageContent
        from datetime import datetime
        
        # 메시지 생성 테스트
        message = Message(
            message_id="test-123",
            channel=Channel(channel_id="test-channel", channel_name="Test Channel"),
            author=Author(author_id="test-user", author_name="Test User"),
            content=MessageContent(text="Hello, world!"),
            timestamp=datetime.now()
        )
        
        assert message.content.text == "Hello, world!"
        print("✅ Message model creation OK")
        return True
        
    except Exception as e:
        print(f"❌ Message model test failed: {e}")
        return False

def test_service_instantiation():
    """서비스 인스턴스 생성 테스트 (실제 연결 없이)"""
    print("\n🧪 Testing Service instantiation...")
    
    try:
        from naraninyeo.adapters.repositories import MessageRepository
        from naraninyeo.adapters.clients import LLMClient, EmbeddingClient
        from naraninyeo.services.message_service import MessageService
        
        # Mock 객체들로 서비스 생성
        repo = MessageRepository()
        llm_client = LLMClient()
        embedding_client = EmbeddingClient()
        
        service = MessageService(repo, llm_client, embedding_client)
        
        print("✅ Service instantiation OK")
        return True
        
    except Exception as e:
        print(f"❌ Service instantiation failed: {e}")
        return False

def main():
    """전체 테스트 실행"""
    print("🚀 Starting refactored code tests...\n")
    
    tests = [
        test_imports,
        test_di_container,
        test_message_creation,
        test_service_instantiation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
    
    print(f"\n📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Refactoring successful!")
    else:
        print("⚠️ Some tests failed. Need investigation.")

if __name__ == "__main__":
    main()
