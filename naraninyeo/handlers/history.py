from datetime import datetime, timezone
from naraninyeo.models.message import Message
from naraninyeo.core.database import mc

async def get_history(room:str, timestamp: datetime, limit: int = 10) -> list[Message]:
    """
    메시지 기록을 가져옵니다.
    """
    
    # 이전 메시지 가져오기
    before_messages = await mc.db["messages"].find(
        {"channel.channel_id": room, "timestamp": {"$lt": timestamp}}
    ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    
    # 이후 메시지 가져오기
    after_messages = await mc.db["messages"].find(
        {"channel.channel_id": room, "timestamp": {"$gte": timestamp}}
    ).sort("timestamp", 1).limit(limit).to_list(length=limit)
    
    # 이전 메시지는 시간 역순으로 정렬되어 있으므로 다시 뒤집어서 시간순으로 만듦
    before_messages.reverse()
    
    # 두 결과를 합치고 limit개만큼만 가져옴
    all_messages = before_messages + after_messages
    if len(all_messages) > limit:
        # 시간순으로 정렬되어 있으므로 중간에서 limit개만큼만 가져옴
        start_idx = (len(all_messages) - limit) // 2 + 1
        all_messages = all_messages[start_idx:start_idx + limit]
    
    return [Message.model_validate(message) for message in all_messages]
