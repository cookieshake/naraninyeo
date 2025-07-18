from naraninyeo.models.message import Message


async def should_respond(request: Message) -> bool:
    """
    메시지가 응답이 필요한지 확인합니다.
    """
    if request.author.author_name == "나란잉여":
        return False
    if request.content.text.startswith('/'):
        return True
    return False
