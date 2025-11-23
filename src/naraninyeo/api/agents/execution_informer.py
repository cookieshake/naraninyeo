from pydantic import BaseModel
from pydantic_ai import ModelSettings, RunContext
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import Message, ResponsePlan


class ExecutionInformerDeps(BaseModel):
    plan: ResponsePlan
    incoming_message: Message
    history_messages: list[Message]
    is_retry: bool


class ExecutionInformerOutput(BaseModel):
    message: str


execution_informer = StructuredAgent(
    name="Execution Informer",
    model=FallbackModel(
        OpenAIChatModel("google/gemini-2.5-flash-lite-preview-09-2025", provider=OpenRouterProvider()),
        OpenAIChatModel("qwen/qwen3-next-80b-a3b-instruct", provider=OpenRouterProvider()),
    ),
    model_settings=ModelSettings(
        extra_body={
            "reasoning": {
                "effort": "minimum",
                "enabled": False,
            },
        }
    ),
    deps_type=ExecutionInformerDeps,
    output_type=ExecutionInformerOutput,
)


@execution_informer.instructions
async def instructions(_: RunContext[ExecutionInformerDeps]) -> str:
    return """
당신은 메시지 답변생성 시스템의 일부입니다.
메시지에 답변하기 위해 자료를 조사하고 답변을 생성하는 동안,
이용자가 심심하지 않도록 하는 간단한 메시지를 작성하세요.

아래의 사항을 지켜주세요.
- 한국어 반말을 사용하세요.
- 간단한 메시지를 작성하세요.
- 질문을 하지 마세요.
"""


@execution_informer.user_prompt
async def user_prompt(deps: ExecutionInformerDeps) -> str:
    if deps.is_retry:
        additional_prompt = "\n이전에 답변을 생성하려고 했지만, 다시 시도중이라는 사실을 알려주세요."
    else:
        additional_prompt = ""
    return f"""
[직전 대화 기록]
{"\n".join(msg.preview for msg in deps.history_messages)}

[응답할 사용자 메시지]
{deps.incoming_message.content.text}

[계획된 조사 활동]
{"".join(f"- {action.action_type}: {action.description}\n" for action in deps.plan.actions)}

위 내용을 참고하여 간단한 메시지를 작성해주세요.{additional_prompt}"""
