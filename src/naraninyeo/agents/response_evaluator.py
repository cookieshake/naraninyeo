from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings, OpenRouterReasoning

from naraninyeo.agents.base import StructuredAgent
from naraninyeo.core.models import Bot, EvaluationFeedback, Message


class ResponseEvaluatorDeps(BaseModel):
    bot: Bot
    incoming_message: Message
    latest_messages: list[Message]
    generated_responses: list[str]


response_evaluator = StructuredAgent(
    name="Response Evaluator",
    model=OpenRouterModel("x-ai/grok-4.1-fast"),
    model_settings=OpenRouterModelSettings(
        openrouter_reasoning=OpenRouterReasoning(
            effort="low",
            enabled=False,
        ),
    ),
    deps_type=ResponseEvaluatorDeps,
    output_type=EvaluationFeedback,
)


@response_evaluator.instructions
async def instructions(_: RunContext[ResponseEvaluatorDeps]) -> str:
    return """
당신은 채팅방에 보낼 응답 초안을 평가하는 역할을 합니다.

다음 체크리스트를 기준으로 응답 초안을 평가하세요:
1. 질문 답변 여부: 사용자의 질문/요청에 실제로 답하고 있는가?
2. 형식 준수:
   - 한국어 반말을 사용하고 있는가?
   - 마크다운 문법(#, *, -, ```)을 사용하지 않는가?
   - "검색 결과에 따르면" 같은 표현이 없는가?
   - "시간 이름: 메시지" 형식을 사용하지 않는가?
3. 적절한 길이: 간단한 질문에 지나치게 긴 답변을 하지 않는가?

판단 기준:
- 사용자 질문에 답하지 못하거나 엉뚱한 내용이면 → 'regather' (정보 재수집)
- 내용은 있지만 응답 자체가 형식 위반이거나 부자연스러우면 → 'generate_again' (응답만 재생성)
- 응답이 적절하면 → 'finalize'
"""


@response_evaluator.user_prompt
async def user_prompt(deps: ResponseEvaluatorDeps) -> str:
    latest_messages_str = "\n".join(msg.preview for msg in deps.latest_messages)
    return f"""
## 응답할 메시지 이전 대화
```
{latest_messages_str}
```

## 응답할 메시지
```
{deps.incoming_message.preview}
```

## 생성된 응답 초안
```
{"\n".join(deps.generated_responses)}
```

이 정보를 바탕으로 생성된 응답 초안을 평가하고, 적절한 피드백을 반환하세요.
"""
