from fastapi import APIRouter
from naraninyeo.models.message import MessageRequest, MessageResponse
from naraninyeo.services.message import save_message, should_respond
from naraninyeo.services.response import get_random_response

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
    # Save user's message
    await save_message(request)
    
    needs_response = should_respond(request.content)
    if needs_response:
        response_message = get_random_response()
        # Save bot's response
        await save_message(request, is_bot=True)
        return MessageResponse(
            do_reply=True,
            message=response_message
        )
    
    return MessageResponse(
        do_reply=False,
        message=""
    )
