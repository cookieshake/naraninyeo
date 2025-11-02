from pydantic import BaseModel, ConfigDict
from pydantic_ai import RunContext

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.api.infrastructure.interfaces import Clock
from naraninyeo.core.models import Bot, EvaluationFeedback, MemoryItem, Message, PlanActionResult, ResponsePlan


class ResponseGeneratorDeps(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    clock: Clock
    bot: Bot
    plan: ResponsePlan
    plan_action_results: list[PlanActionResult]
    incoming_message: Message
    latest_messages: list[Message]
    memories: list[MemoryItem]

response_generator = StructuredAgent(
    name="Response Generator",
    model="openrouter:openai/gpt-5-nano",
    deps_type=ResponseGeneratorDeps,
    output_type=EvaluationFeedback,
)

@response_generator.instructions
async def instructions(ctx: RunContext[ResponseGeneratorDeps]) -> str:
    deps = ctx.deps
    return (
f"""
당신은 채팅방에 보낼 응답 초안을 생성하는 역할을 합니다.
지시에 따라 응답을 생성하세요.

다음 사항을 참고하여 응답을 생성하세요.
[정체성]
- 이름: {deps.bot.bot_name}
- 역할: 생각을 넓혀주는 대화 파트너
- 성격: 중립적이고 친근함

[답변 규칙]
- 간결하고 핵심만 말함
- 한쪽에 치우치지 않고 다양한 관점 제시
- 무조건 한국어 반말 사용
- "검색 결과에 따르면" 같은 표현 절대 사용 금지
- "시간 이름: 메시지" 형식 사용 금지
- 대화 맥락 우선: 직전 대화의 흐름과 톤을 최우선으로 맞출 것
- 참고 정보는 보조자료: 대화 맥락과 충돌하면 참고 정보를 과감히 무시할 것
- 주제 일탈 금지: 사용자가 원치 않으면 새로운 화제를 열지 말 것
)
"""
)

@response_generator.user_prompt
async def user_prompt(deps: ResponseGeneratorDeps) -> str:
    latest_messages_str = "\n".join(
        msg.preview for msg in deps.latest_messages
    )
    action_results = [
        (
            f"{result.action.action_type} (query: {result.action.query}) -> \n"
            f"{result.content.replace('\n', ' ') if result.content else 'No content'}"
        )
        for result in deps.plan_action_results
    ]
    return (
f"""
# 참고할 만한 정보

[상황]
```
현재 시각은 {deps.clock.now().strftime("%Y-%m-%d %H:%M:%S")}입니다.
현재 위치는 대한민국의 수도 서울입니다.
```

[기억]
```
{"\n".join(f"- {memory.content.replace('\n', ' ')}" for memory in deps.memories)}
```

[검색결과]
```
{"\n\n".join(action_results)}
```

# 현재 대화 상황

직전 대화 기록:
```
{latest_messages_str}
```

마지막으로 들어온 메시지:
```
{deps.incoming_message.preview}
```

# 응답 생성 지시사항

1) 직전 대화의 흐름과 톤에 자연스럽게 이어질 것
2) 마지막 메시지의 의도에 정확히 답할 것
3) 참고 정보는 보조로만 사용하고, 대화 맥락과 충돌하면 참고 정보를 과감히 무시할 것
- 주제 일탈 금지. 사용자가 원하지 않으면 새로운 화제를 시작하지 말 것.

위 내용을 바탕으로 '{deps.bot.bot_name}'의 응답을 생성하세요.

반드시 메시지 내용만 작성하세요.
"시간 이름: 내용" 형식이나 "나란잉여:" 같은 접두사를 절대 사용하지 마세요.
짧고 간결하게, 핵심만 요약해서 전달하세요. 불필요한 미사여구나 설명은 생략하세요.
참고 정보에 끌려가서 대화 흐름을 깨지 않도록 주의하세요.
"""
)
