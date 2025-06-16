from datetime import datetime
from naraninyeo.models.message import MessageDocument
from naraninyeo.core.database import db

async def get_history(room:str, timestamp: datetime = None, limit: int = 10) -> list[MessageDocument]:
    """
    메시지 기록을 가져옵니다.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    # 이전 메시지 가져오기
    before_messages = await db.get_db.messages.find(
        {"room": room, "created_at": {"$lt": timestamp}}
    ).sort("created_at", -1).limit(limit).to_list(length=limit)
    
    # 이후 메시지 가져오기
    after_messages = await db.get_db.messages.find(
        {"room": room, "created_at": {"$gte": timestamp}}
    ).sort("created_at", 1).limit(limit).to_list(length=limit)
    
    # 이전 메시지는 시간 역순으로 정렬되어 있으므로 다시 뒤집어서 시간순으로 만듦
    before_messages.reverse()
    
    # 두 결과를 합치고 limit개만큼만 가져옴
    all_messages = before_messages + after_messages
    if len(all_messages) > limit:
        # 시간순으로 정렬되어 있으므로 중간에서 limit개만큼만 가져옴
        start_idx = (len(all_messages) - limit) // 2
        all_messages = all_messages[start_idx:start_idx + limit]
    
    return [MessageDocument.model_validate(message) for message in all_messages]
