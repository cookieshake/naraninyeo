from typing import Annotated, Literal, Union
from datetime import datetime
from zoneinfo import ZoneInfo

from naraninyeo.repository.message import get_history

async def get_history_by_timestamp(
    room_id: Annotated[str, "The room id to get the history from"],
    timestamp: Annotated[str, "The timestamp to get the history from. (YYYY-MM-DD HH:MM:SS) KST"],
    limit: Annotated[float, "The number of messages to get. (default: 10)"] = 10.0
) -> str:
    """
    Retrieves message history from a specified room based on a given timestamp.
    
    This function fetches messages around the specified timestamp, getting both previous 
    and subsequent messages to provide conversational context around that point in time.
    The function balances the retrieval to show messages before and after the timestamp.
    """
    
    # Convert KST timestamp string to datetime with KST timezone
    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    history = await get_history(room_id, dt, int(limit))

    result = []
    for message in history:
        result.append(message.text_repr)
    return "\n".join(result)