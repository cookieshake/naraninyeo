from pydantic import BaseModel
from pydantic_ai import RunContext

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import Message


class MemoryExtractorDeps(BaseModel):
    latest_messages: list[Message]

memory_extractor = StructuredAgent(
    name="Memory Extractor",
    model="openrouter:openai/gpt-4.1-nano",
    deps_type=MemoryExtractorDeps,
    output_type=list[str],
)

@memory_extractor.instructions
async def instructions(ctx: RunContext[MemoryExtractorDeps]) -> str:
    return (
"""
당신은 대화 메시지 목록에서 기억 항목을 추출하는 역할을 합니다.
각 메시지를 분석하고, 중요한 정보나 반복적으로 언급되는 내용을 기억 항목으로 변환해야 합니다.

다음 사항을 고려하여 기억 항목을 생성하세요.
- 중요한 사실, 이벤트, 날짜, 인물 등을 포함하세요.
- 기억 항목은 간결하고 명확해야 합니다.
- 100자 이내로 작성하세요.
"""
)

@memory_extractor.user_prompt
async def user_prompt(deps: MemoryExtractorDeps) -> str:
    messages_str = "\n".join(
        msg.preview for msg in deps.latest_messages
    )
    return (
f"""
다음 대화 메시지 목록에서 기억 항목을 추출하세요.

## 대화 메시지 목록:
```
{messages_str}
```
"""
)
