# 나란잉여를 cli로 실행하고 메시지를 주고받는 테스트

import asyncio
from datetime import datetime
import uuid
from naraninyeo.services.message import handle_message
from naraninyeo.models.message import Message, Channel, Author, MessageContent
from naraninyeo.core.database import mc

async def main():
    await mc.connect_to_database()
    # 모든 메시지 기록 삭제
    await mc.db.messages.delete_many({"channel.channel_id": "test"})
    try:
        while True:
            text = input("유저: ")
            if text == "exit":
                break
            message = Message(
                message_id=str(uuid.uuid4()),
                channel=Channel(channel_id="test", channel_name="test"),
                author=Author(author_id="test", author_name="유저"),
                content=MessageContent(text=text),
                timestamp=datetime.now()
            )
            async for reply in handle_message(message):
                if reply:
                    print(f"나란잉여: {reply.content.text}")
    finally:
        await mc.close_database_connection()

if __name__ == "__main__":
    asyncio.run(main())