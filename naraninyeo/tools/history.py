from typing import Annotated, Literal
from datetime import datetime
from zoneinfo import ZoneInfo
from haystack.tools import tool

from naraninyeo.handlers.history import get_history

@tool
def get_history_by_timestamp(
    room_id: Annotated[str, "The room id to get the history from"],
    timestamp: Annotated[str, "The timestamp to get the history from. (YYYY-MM-DD HH:MM:SS) KST"],
    limit: Annotated[int, "The number of messages to get. (default: 10)"] = 10
) -> str:
    """
    Retrieves message history from a specified room based on a given timestamp.
    
    This function fetches messages around the specified timestamp, getting both previous 
    and subsequent messages to provide conversational context around that point in time.
    The function balances the retrieval to show messages before and after the timestamp.
    """
    import asyncio
    
    # Convert KST timestamp string to datetime with KST timezone
    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Seoul"))
    history = asyncio.run(get_history(room_id, dt, limit))

    result = []
    for message in history:
        result.append(f"{message.created_at.astimezone(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S')} {message.author_name} : {message.content[:50]}")
    return "\n".join(result)