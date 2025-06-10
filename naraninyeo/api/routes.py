from fastapi import APIRouter
from naraninyeo.models.message import MessageRequest, MessageResponse

router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Hello World"}

@router.post("/new_message", response_model=MessageResponse)
async def handle_message(request: MessageRequest) -> MessageResponse:
    """
    Handle incoming messages and return a response.
    """
    # 여기서 메시지 처리 로직을 구현할 수 있습니다
    # 예: 특정 키워드에 대한 응답, 메시지 필터링 등
    return MessageResponse(
        do_reply=True,
        message=request.content  # 원본 메시지 내용을 그대로 반환
    ) 
