from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings, OpenRouterReasoning

from naraninyeo.agents.base import StructuredAgent
from naraninyeo.core.models import Message


class ProfanityCheckerDeps(BaseModel):
    incoming_message: Message


class ProfanityCheckerOutput(BaseModel):
    is_profane: bool
    reason: str


profanity_checker = StructuredAgent(
    name="Profanity Checker",
    model=OpenRouterModel("google/gemini-3.1-flash-lite-preview"),
    model_settings=OpenRouterModelSettings(
        openrouter_reasoning=OpenRouterReasoning(
            effort="low",
            enabled=False,
        ),
    ),
    deps_type=ProfanityCheckerDeps,
    output_type=ProfanityCheckerOutput,
)


@profanity_checker.instructions
async def instructions(_: RunContext[ProfanityCheckerDeps]) -> str:
    return """
당신은 사용자의 메시지에 봇을 향한 욕설이 포함되어 있는지만 검사하는 역할을 합니다.

**차단 기준 — is_profane=True인 경우**:
- 봇을 향해 실제 욕설(비속어, 욕)을 사용한 경우만 해당
- 예: "씨발", "개새끼", "꺼져", "병신" 등 욕이 포함된 경우

**반드시 통과시킬 것 (is_profane=False)**:
- 명령조, 고압적 말투, 반말 — 욕이 없으면 통과
- 불만, 짜증, 감정적 표현 — 욕이 없으면 통과
- 제3자에 대한 험담이나 욕 — 봇을 향한 게 아니면 통과
- 민감한 주제(범죄, 정치 등)에 대한 질문 — 통과

결과로 'is_profane' 필드에 부적절함 여부(True/False)를,
'reason' 필드에 그 이유를 한국어로 매우 간결하게(단어 혹은 짧은 구) 작성하세요.
"""


@profanity_checker.user_prompt
async def user_prompt(deps: ProfanityCheckerDeps) -> str:
    return f"""
## 검사할 메시지
```
{deps.incoming_message.content.text}
```

이 메시지가 부적절한지 검사한 결과를 반환하세요.
"""
