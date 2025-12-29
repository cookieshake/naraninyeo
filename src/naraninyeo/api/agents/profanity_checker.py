from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings, OpenRouterReasoning

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import Message


class ProfanityCheckerDeps(BaseModel):
    incoming_message: Message


class ProfanityCheckerOutput(BaseModel):
    is_profane: bool
    reason: str


profanity_checker = StructuredAgent(
    name="Profanity Checker",
    model=OpenRouterModel("openai/gpt-4.1-nano"),
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
당신은 사용자의 메시지가 욕설이나 인신공격을 포함하고 있는지 검사하는 역할을 합니다.

다음 기준에 따라 메시지를 평가하세요:
- 욕설이나 비속어가 포함되어 있는가?
- 특정 개인이나 집단에 대한 인신공격이 포함되어 있는가?

**주의사항**:
- 핵무기, 범죄 등 위험하거나 자극적인 주제에 대한 질문이라도,
  욕설이나 특정인에 대한 공격이 없다면 'is_profane'을 False로 판단하세요.
- 오직 언어 폭력(욕설)과 인신공격만을 차단 대상으로 합니다.

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
