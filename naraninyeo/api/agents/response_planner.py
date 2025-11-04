from pydantic import BaseModel
from pydantic_ai import ModelSettings, NativeOutput, RunContext

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import ActionType, Bot, MemoryItem, Message, ResponsePlan


class ResponsePlannerDeps(BaseModel):
    bot: Bot
    incoming_message: Message
    latest_messages: list[Message]
    memories: list[MemoryItem]


response_planner = StructuredAgent(
    name="Response Planner",
    model="openrouter:x-ai/grok-4-fast",
    model_settings=ModelSettings(
        extra_body={
            "reasoning": {
                "effort": "low",
                "enabled": False,
            },
        }
    ),
    deps_type=ResponsePlannerDeps,
    output_type=ResponsePlan,
)


@response_planner.instructions
async def instructions(ctx: RunContext[ResponsePlannerDeps]) -> str:
    return f"""
당신은 사용자의 질문에 답하기 위해 어떤 정보를 검색해야 할지 계획하는 AI입니다.
사용자의 질문, 대화 기록, 단기 기억을 바탕으로 아래 타입 중 필요한 것을 선택하여 계획하세요.

현재 시간은 {ctx.deps.incoming_message.timestamp_iso} 입니다.

사용 가능한 검색 타입:
- {ActionType.SEARCH_WEB_NEWS}: 최신 뉴스를 찾을 때
- {ActionType.SEARCH_WEB_BLOG}: 개인 경험/후기를 찾을 때
- {ActionType.SEARCH_WEB_GENERAL}: 일반 웹 페이지 전반 탐색
- {ActionType.SEARCH_WEB_SCHOLAR}: 학술/문서 기반 정보
- {ActionType.SEARCH_CHAT_HISTORY}: 과거 대화 내용 탐색

아래의 지침을 따르세요:
- 필요 없으면 빈 배열을 반환하고, 필요한 경우 여러 타입을 조합할 수 있습니다.
- query를 포함하지 않은 검색은 계획에 포함하지 말고 설명도 작성하지 마세요.
- 각 계획에는 적절한 query와 description을 포함하세요.
- 쿼리에 현재 시간이 필요할 경우 이를 반영하세요.
- '오늘', '최근' 등의 표현은 사용하지 말고 구체적인 날짜를 명시하세요.
- 날짜는 년, 월 등의 인간에게 친숙한 형식을 사용하세요.
"""


@response_planner.user_prompt
async def user_prompt(deps: ResponsePlannerDeps) -> str:
    latest_messages_str = "\n".join(msg.preview for msg in deps.latest_messages)
    memories_str = "\n".join(f"- {mem.content}" for mem in deps.memories)
    return f"""
## 봇 정보
```
이름: {deps.bot.bot_name}
```

## 기억
```
{memories_str}
```

## 직전 대화 기록
```
{latest_messages_str}
```

## 새로 들어온 메시지
```
{deps.incoming_message.preview}
```

위 새로 들어온 메시지에 답하기 위해 어떤 종류의 검색을 어떤 검색어로 해야할까요?
참고할만한 예전 대화 기록을 활용하여 더 정확한 검색 계획을 수립하세요.
"""
