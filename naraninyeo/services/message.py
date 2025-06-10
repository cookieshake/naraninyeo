from naraninyeo.models.message import MessageRequest, MessageDocument
from naraninyeo.core.database import db
from motor.motor_asyncio import UpdateOne

def should_respond(message: str) -> bool:
    """
    Determine if we should respond to the message.
    Returns True if the message starts with '/', False otherwise.
    """
    return message.strip().startswith('/')

async def save_message(message_request: MessageRequest, is_bot: bool = False) -> None:
    """
    Save message to database with simplified fields.
    If a message with the same logId exists, it will be updated.
    
    Args:
        message_request: The message request to save
        is_bot: Whether this is a bot's response message
    """
    message_doc = MessageDocument(
        _id=f"{message_request.logId}{'_bot' if is_bot else ''}",
        room_id=message_request.room,
        author_name=message_request.author.name,
        content=message_request.content
    )
    
    # Use upsert to handle duplicates
    await db.get_db.messages.update_one(
        {"_id": message_doc.message_id},
        {"$set": message_doc.model_dump(by_alias=True)},
        upsert=True
    ) 