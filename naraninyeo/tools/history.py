from typing import Annotated, Literal, Union
from datetime import datetime
from zoneinfo import ZoneInfo

from naraninyeo.repository.message import get_history

async def get_history_by_timestamp(
    room_id: Annotated[str, "기록을 가져올 방의 ID"],
    timestamp: Annotated[str, "기록을 가져올 기준 시간 (YYYY-MM-DD HH:MM:SS) KST"],
) -> str:
    """
    주어진 타임스탬프를 기준으로 특정 방의 메시지 기록을 검색합니다.

    이 함수는 지정된 타임스탬프를 중심으로 이전 10개와 이후 10개의 메시지를 가져와
    해당 시점의 대화 맥락을 파악할 수 있도록 총 20개의 메시지를 제공합니다.
    """
    
    # Convert KST timestamp string to datetime with KST timezone
    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    
    history_before = await get_history(room_id, dt, limit=10, before=True)
    history_after = await get_history(room_id, dt, limit=10, before=False)
    history = history_before + history_after

    result = []
    for message in history:
        result.append(message.text_repr)
    return "\n".join(result)