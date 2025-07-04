from datetime import datetime, timezone
from naraninyeo.models.message import Message
from naraninyeo.core.database import mc

async def get_history(room:str, timestamp: datetime, limit: int = 10) -> list[Message]:
    """
    주어진 timestamp보다 작거나 같은 메시지를 limit개만큼 가져옵니다.
    """
    
    # timestamp보다 작거나 같은 메시지들을 시간순으로 가져오기
    messages = await mc.db["messages"].find(
        {"channel.channel_id": room, "timestamp": {"$lte": timestamp}}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    messages.reverse()
    
    return [Message.model_validate(message) for message in messages]
