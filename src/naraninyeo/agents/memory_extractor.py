from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings, OpenRouterReasoning

from naraninyeo.agents.base import StructuredAgent
from naraninyeo.core.models import Message


class MemoryExtractorDeps(BaseModel):
    latest_messages: list[Message]
    existing_memories: list[str] = []


memory_extractor = StructuredAgent(
    name="Memory Extractor",
    model=OpenRouterModel("deepseek/deepseek-v3.2"),
    model_settings=OpenRouterModelSettings(
        openrouter_reasoning=OpenRouterReasoning(
            effort="low",
            enabled=False,
        ),
    ),
    deps_type=MemoryExtractorDeps,
    output_type=list[str],
)


@memory_extractor.instructions
async def instructions(ctx: RunContext[MemoryExtractorDeps]) -> str:
    return """
당신은 대화 메시지에서 사용자에 관한 기억 항목을 추출하는 역할을 합니다.
봇의 발언은 무시하고, 사용자의 발언만 분석하세요.

[추출 대상]
- 사용자의 개인정보: 이름, 나이, 직업, 거주지 등
- 선호도 및 취향: 좋아하는 것, 싫어하는 것
- 습관 및 패턴: 자주 하는 행동, 루틴
- 중요한 일정, 목표, 계획
- 언급된 주변 인물 및 관계

[추출 제외]
- 단순 인사, 감사 표현 ("안녕", "ㄱㅅ", "ㅋㅋ")
- 일시적 대화 맥락 (지금 대화에서만 의미 있는 내용)
- 이미 기억에 있는 내용과 동일하거나 매우 유사한 내용

[형식]
- 100자 이내로 간결하게
- 주어를 "사용자"로 명시하지 말고 사실 그대로 서술 (예: "파이썬 개발자")
- 추출할 내용이 없으면 빈 배열 반환
"""


@memory_extractor.user_prompt
async def user_prompt(deps: MemoryExtractorDeps) -> str:
    messages_str = "\n".join(msg.preview for msg in deps.latest_messages)
    existing_str = "\n".join(f"- {m}" for m in deps.existing_memories) if deps.existing_memories else "없음"
    return f"""
## 이미 저장된 기억 (중복 추출 금지):
{existing_str}

## 대화 메시지:
```
{messages_str}
```

위 대화에서 새로운 기억 항목만 추출하세요.
"""
