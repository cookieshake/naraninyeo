from typing import List, Literal, TypeAlias

from pydantic import BaseModel
from pydantic_ai import NativeOutput, RunContext
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import MemoryItem


class MemoryPrunerDeps(BaseModel):
    memories: list[MemoryItem]


class MemoryMergeAction(BaseModel):
    method: Literal["merge"]
    ids: list[int]
    merged_content: str


class MemoryDeleteAction(BaseModel):
    method: Literal["delete"]
    ids: list[int]


MemoryPrunerAction: TypeAlias = MemoryMergeAction | MemoryDeleteAction

memory_pruner = StructuredAgent(
    name="Memory Pruner",
    model=FallbackModel(
        OpenAIChatModel("openai/gpt-4.1-nano", provider=OpenRouterProvider()),
        OpenAIChatModel("google/gemini-2.5-flash-lite", provider=OpenRouterProvider()),
    ),
    deps_type=MemoryPrunerDeps,
    output_type=List[MemoryPrunerAction],
)


@memory_pruner.instructions
async def instructions(_: RunContext[MemoryPrunerDeps]) -> str:
    return """
당신은 기억 항목 목록을 검토하고, 불필요하거나 중복된 항목을 제거하는 역할을 합니다.
다음 사항을 고려하여 기억 항목을 선별하세요.
- 중복된 정보는 제거하세요.
- 중요하지 않은 세부사항은 생략하세요.
- 기억 항목은 간결하고 명확해야 합니다.
- 100자 이내로 작성하세요.
- 가능한 한 적은 수의 기억 항목으로 요약하세요.

병합할 기억 항목이 있다면, 'merge' method와 해당 기억 항목의 ID 목록을 포함하는 객체를 반환하세요.
삭제할 기억 항목이 있다면, 'delete' method와 해당 기억 항목의 ID 목록을 포함하는 객체를 반환하세요.

[예시]
```json
[
    {
        "method": "merge",
        "ids": [1, 2],
        "merged_content": "병합된 기억 항목의 내용"
    },
    {
        "method": "delete",
        "ids": [3]
    }
]
```
"""


@memory_pruner.user_prompt
async def user_prompt(deps: MemoryPrunerDeps) -> str:
    memories = [f"ID {i + 1}: {mem.content.replace('\n', ' ')}" for i, mem in enumerate(deps.memories)]
    memories_str = "\n".join(memories)
    return f"""
다음 기억 항목 목록을 검토하고, 불필요하거나 중복된 항목을 제거하세요.

## 기억 항목 목록:
{memories_str}
"""
