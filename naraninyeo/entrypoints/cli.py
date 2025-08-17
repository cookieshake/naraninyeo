"""
나란잉여를 CLI로 실행하고 메시지를 주고받는 테스트 클라이언트
"""

import asyncio
from datetime import datetime
import uuid
import traceback

from naraninyeo.domain.application.new_message_handler import NewMessageHandler

from naraninyeo.di import container
from naraninyeo.domain.model.message import Author, Channel, Message, MessageContent

class LocalClient:
    """로컬 테스트 클라이언트"""
    
    def __init__(self):
        pass

    async def initialize(self):
        """클라이언트 초기화"""
        print("🚀 나란잉여 로컬 클라이언트 시작!")
                
        # 서비스 및 어댑터 가져오기
        self.new_message_handler = await container.get(NewMessageHandler)
        print("✅ 대화 서비스 준비 완료")
    
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
                    content=MessageContent(text=text, attachments=[]),
                    timestamp=datetime.now()
                )
                
                # 메시지 처리 (저장 + 응답 생성) - 통합 서비스 사용
                print("💾 메시지 처리 중...")
                response_count = 0
                async for reply in self.new_message_handler.handle(message):
                    response_count += 1
                    if reply:
                        print(f"🤖 나란잉여: {reply.content.text}")
                
                if response_count == 0:
                    print("💭 (봇이 응답하지 않습니다. '/'로 시작하는 메시지를 보내보세요)")
        
        except Exception as e:
            print(f"❌ 대화 중 오류 발생: {e}")
            traceback.print_exc()
    
    async def cleanup(self):
        """정리 작업"""
        print("\n🧹 정리 작업 중...")
        try:
            # 컨테이너 종료 (데이터베이스 연결 해제 포함)
            await container.close()
            print("✅ Dishka 컨테이너 종료 완료")
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
        traceback.print_exc()
    
    finally:
        # 정리
        await client.cleanup()
