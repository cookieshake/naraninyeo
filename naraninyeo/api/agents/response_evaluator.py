from pydantic import BaseModel
from pydantic_ai import RunContext

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import Bot, EvaluationFeedback, Message, ResponsePlan


class ResponseEvaluatorDeps(BaseModel):
    bot: Bot
    plan: ResponsePlan
    incoming_message: Message
    latest_messages: list[Message]
    generated_responses: list[str]

response_evaluator = StructuredAgent(
    name="Response Evaluator",
    model="openrouter:openai/gpt-4.1-nano",
    deps_type=ResponseEvaluatorDeps,
    output_type=EvaluationFeedback,
)

@response_evaluator.instructions
async def instructions(_: RunContext[ResponseEvaluatorDeps]) -> str:
    return (
"""
당신은 채팅방에 보낼 응답 초안을 평가하는 역할을 합니다.
응답 초안은 LLM이 생성한 계획에 따라 작성되었습니다.

다음 사항을 고려하여 응답 초안을 평가하세요.
- 응답이 사용자의 질문이나 요청에 적절히 답변하는가?
- 응답이 명확하고 이해하기 쉬운가?

만약 응답 계획부터 다시 세워야 한다고 판단되면 'plan_again'을 반환하세요.
만약 응답 계획은 적절하지만, 실행 결과를 다시 시도해야 한다고 판단되면 'execute_again'을 반환하세요.
만약 응답 실행은 적절하지만, 생성된 응답이 부적절하다고 판단되면 'generate_again'을 반환하세요.
만약 응답이 적절하다고 판단되면 'finalize'를 반환하세요.
"""
)

@response_evaluator.user_prompt
async def user_prompt(deps: ResponseEvaluatorDeps) -> str:
    latest_messages_str = "\n".join(
        msg.preview for msg in deps.latest_messages
    )
    return (
f"""
## 응답할 메시지 이전 대화
```
{latest_messages_str}
```

## 응답할 메시지
```
{deps.incoming_message.preview}
```

## 응답 계획
```
{deps.plan.summary}
```

## 생성된 응답 초안
```
{"\n".join(deps.generated_responses)}
```

이 정보를 바탕으로 생성된 응답 초안을 평가하고, 적절한 피드백을 반환하세요.
"""
)
