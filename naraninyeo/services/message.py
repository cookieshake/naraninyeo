from naraninyeo.models.message import MessageRequest, MessageDocument
from naraninyeo.core.database import db

async def save_message(message_request: MessageRequest) -> None:
    """
    Save message to database
    """
    message_doc = MessageDocument(**message_request.model_dump())
    await db.get_db.messages.insert_one(message_doc.model_dump()) 