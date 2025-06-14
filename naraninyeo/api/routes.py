from fastapi import APIRouter
from naraninyeo.models.message import MessageRequest, MessageResponse
from naraninyeo.services.message import save_message, should_respond, get_response

router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Hello World"}

@router.post("/new_message", response_model=MessageResponse)
async def handle_message(request: MessageRequest) -> MessageResponse:
    """
    Handle incoming messages and save them to MongoDB.
    Only respond if the message starts with '/'.
    """
    needs_response = await should_respond(request)
    response_message = await get_response(request) if needs_response else None
    
    # Save message with response if any
    await save_message(request, response_message)
    
    return MessageResponse(
        do_reply=needs_response,
        message=response_message if needs_response else ""
    )
