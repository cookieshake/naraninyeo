from fastapi import APIRouter
from naraninyeo.models.message import MessageRequest, MessageResponse
from naraninyeo.services.message import save_message
from naraninyeo.services.response import get_random_response

router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Hello World"}

@router.post("/new_message", response_model=MessageResponse)
async def handle_message(request: MessageRequest) -> MessageResponse:
    """
    Handle incoming messages and save them to MongoDB.
    """
    await save_message(request)
    return MessageResponse(
        do_reply=True,
        message=get_random_response()
    )
