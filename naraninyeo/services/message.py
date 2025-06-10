from naraninyeo.models.message import MessageRequest, MessageDocument
from naraninyeo.core.database import db
from typing import Optional

def should_respond(message: str) -> bool:
    """
    Determine if we should respond to the message.
    Returns True if the message starts with '/', False otherwise.
    """
    return message.strip().startswith('/')

async def save_message(message_request: MessageRequest, response_content: Optional[str] = None) -> None:
    """
    Save message to database with simplified fields.
    If a message with the same logId exists, it will be updated.
    
    Args:
        message_request: The message request to save
        response_content: The bot's response content if any
    """
    message_doc = MessageDocument(
        _id=message_request.logId,
        room=message_request.room,
        channel_id=message_request.channelId,
        author_name=message_request.author.name,
        content=message_request.content,
        has_response=response_content is not None,
        response_content=response_content
    )
    
    # Use upsert to handle duplicates
    await db.get_db.messages.update_one(
        {"_id": message_doc.message_id},
        {"$set": message_doc.model_dump(by_alias=True)},
        upsert=True
    ) 