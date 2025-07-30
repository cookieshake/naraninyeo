# 나란잉여를 CLI로 실행하고 메시지를 주고받는 테스트 클라이언트

import asyncio
from datetime import datetime
import uuid

# 새로운 리팩토링된 구조 사용
from naraninyeo.adapters.database import database_adapter
from naraninyeo.container import setup_dependencies, container
from naraninyeo.services.message_service import MessageService
from naraninyeo.models.message import Message, Channel, Author, MessageContent

class LocalClient:
    """로컬 테스트 클라이언트"""
    
    def __init__(self):
        self.message_service = None
    
    async def initialize(self):
        """클라이언트 초기화"""
        print("🚀 나란잉여 로컬 클라이언트 시작!")
        
        # 데이터베이스 연결
        await database_adapter.connect()
        print("✅ 데이터베이스 연결 완료")
        
        # 의존성 주입 설정
        setup_dependencies()
        print("✅ 의존성 주입 설정 완료")
        
        # 서비스 가져오기
        self.message_service = container.get(MessageService)
        print("✅ 메시지 서비스 준비 완료")
        
        # 테스트 채널 메시지 기록 삭제 (선택사항)
        try:
            await database_adapter.db.messages.delete_many({"channel.channel_id": "local-test"})
            print("🧹 이전 테스트 메시지 기록 삭제 완료")
        except Exception as e:
            print(f"⚠️ 이전 기록 삭제 실패 (무시됨): {e}")
    
    async def run_chat_loop(self):
        """대화 루프 실행"""
        print("\n💬 대화를 시작합니다!")
        print("사용법:")
        print("  - 일반 메시지: 그냥 입력하세요")
        print("  - 봇 응답 요청: 메시지 앞에 '/'를 붙이세요")
        print("  - 종료: 'exit' 또는 'quit'")
        print("-" * 50)
        
        try:
            while True:
                # 사용자 입력 받기
                try:
                    text = input("\n🧑 유저: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 대화를 종료합니다!")
                    break
                
                if text.lower() in ["exit", "quit", "종료"]:
                    print("👋 대화를 종료합니다!")
                    break
                
                if not text:
                    print("⚠️ 빈 메시지는 보낼 수 없습니다.")
                    continue
                
                # 메시지 객체 생성
                message = Message(
                    message_id=str(uuid.uuid4()),
                    channel=Channel(channel_id="local-test", channel_name="로컬 테스트"),
                    author=Author(author_id="local-user", author_name="유저"),
                    content=MessageContent(text=text),
                    timestamp=datetime.now()
                )
                
                # 메시지 저장
                await self.message_service.save_message(message)
                print("✅ 메시지 저장됨")
                
                # 응답이 필요한지 확인
                should_respond = await self.message_service.should_respond_to(message)
                
                if should_respond:
                    print("🤖 나란잉여가 응답을 생성 중...")
                    
                    # 응답 생성 및 출력
                    response_count = 0
                    async for reply in self.message_service.generate_response(message):
                        response_count += 1
                        if reply:
                            print(f"🤖 나란잉여: {reply.content.text}")
                            # 응답도 저장
                            await self.message_service.save_message(reply)
                    
                    if response_count == 0:
                        print("🤖 나란잉여: (응답을 생성하지 못했습니다)")
                else:
                    print("💭 (봇이 응답하지 않습니다. '/'로 시작하는 메시지를 보내보세요)")
        
        except Exception as e:
            print(f"❌ 대화 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
    
    async def cleanup(self):
        """정리 작업"""
        print("\n🧹 정리 작업 중...")
        try:
            await database_adapter.disconnect()
            print("✅ 데이터베이스 연결 해제 완료")
        except Exception as e:
            print(f"⚠️ 정리 중 오류 (무시됨): {e}")

async def main():
    """메인 함수"""
    client = LocalClient()
    
    try:
        # 초기화
        await client.initialize()
        
        # 대화 루프 실행
        await client.run_chat_loop()
        
    except Exception as e:
        print(f"❌ 로컬 클라이언트 실행 중 오류: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 정리
        await client.cleanup()

if __name__ == "__main__":
    # 모듈로 실행할 때를 위한 경로 설정
    import sys
    import os
    
    # 프로젝트 루트 디렉토리를 Python 경로에 추가
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    asyncio.run(main())