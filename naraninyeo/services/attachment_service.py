"""첨부파일 관련 서비스"""

import httpx
from naraninyeo.models.message import Attachment
from naraninyeo.core.database import mc

async def create_attachment_with_content_url(
    attachment_id: str,
    attachment_type: str,
    content_url: str
) -> Attachment:
    """URL에서 첨부파일을 생성합니다."""
    async with httpx.AsyncClient() as client:
        response = await client.get(content_url)
        attachment = Attachment(
            attachment_id=attachment_id,
            attachment_type=attachment_type,
            content_type=response.headers.get("Content-Type"),
            content_length=response.headers.get("Content-Length")
        )
        await save_attachment_content(attachment_id, response.content)
        return attachment

async def save_attachment_content(attachment_id: str, content: bytes):
    """첨부파일 내용을 저장합니다."""
    await mc.db["attachment_content"].update_one(
        {"attachment_id": attachment_id},
        {"$set": {"content": content}},
        upsert=True
    )

async def get_attachment_content(attachment_id: str) -> bytes:
    """첨부파일 내용을 가져옵니다."""
    result = await mc.db["attachment_content"].find_one({"attachment_id": attachment_id})
    return result["content"] if result else None
