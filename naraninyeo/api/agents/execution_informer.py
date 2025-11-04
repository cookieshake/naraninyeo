from typing import Literal

from pydantic import BaseModel
from pydantic_ai import NativeOutput, RunContext

from naraninyeo.api.agents.base import StructuredAgent
from naraninyeo.core.models import Message, ResponsePlan


class ExecutionInformerDeps(BaseModel):
    plan: ResponsePlan
    incoming_message: Message
    history_messages: list[Message]


class ExecutionInformerOutput(BaseModel):
    message: str


execution_informer = StructuredAgent(
    name="Execution Informer",
    model="openrouter:x-ai/grok-4-fast",
    deps_type=ExecutionInformerDeps,
    output_type=ExecutionInformerOutput,
)


@execution_informer.instructions
async def instructions(_: RunContext[ExecutionInformerDeps]) -> str:
    return """
메시지에 답변하기 위해 자료를 조사하고 답변을 생성하는 동안,
사용자에게 조사 및 생성을 하겠다고 알리면서, 심심하지 않도록 간단한 메시지를 작성하세요.
"""

@execution_informer.user_prompt
async def user_prompt(deps: ExecutionInformerDeps) -> str:
    return f"""
[직전 대화 기록]
{"\n".join(msg.preview for msg in deps.history_messages)}

[응답할 사용자 메시지]
{deps.incoming_message.content.text}

[계획된 조사 활동]
{"".join(f"- {action.action_type}: {action.description}\n" for action in deps.plan.actions)}
"""
