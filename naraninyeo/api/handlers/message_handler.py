"""Flow that processes newly arriving messages."""

from __future__ import annotations

from typing import Awaitable, Callable, Sequence

from naraninyeo.api.models import FlowResponse, IncomingMessageRequest, MessageProcessingState, MessageResponse
from naraninyeo.core import BotReference, FlowBase, FlowContext, FlowExecutionResult, TaskBase, TenantReference

BotResolver = Callable[[TenantReference], Awaitable[BotReference | None]]


class MessageProcessingFlow(
    FlowBase[MessageProcessingState, MessageProcessingState]
):  # pragma: no cover - orchestrates injected tasks
    """Concrete flow wiring together the message processing tasks."""

    def __init__(self, tasks: Sequence[TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]]) -> None:
        super().__init__(tasks=list(tasks))


class MessageHandler:
    def __init__(
        self,
        flow: MessageProcessingFlow,
        *,
        resolve_bot: BotResolver | None = None,
    ) -> None:
        self._flow = flow
        self._resolve_bot = resolve_bot

    async def handle(self, request: IncomingMessageRequest) -> FlowResponse:
        inbound = request.to_domain()
        tenant = inbound.tenant
        bot = await self._resolve_bot(tenant) if self._resolve_bot else None
        metadata: dict[str, object] = {"tenant": tenant}
        if bot is not None:
            metadata["bot"] = bot
        context: FlowContext = self._flow.build_context(metadata=metadata)
        state = MessageProcessingState(tenant=tenant, bot=bot, inbound=inbound)
        result: FlowExecutionResult[MessageProcessingState] = await self._flow.execute(context, state)
        reply = result.output.reply if result.output else None
        reply_payload = MessageResponse.from_domain(reply) if reply is not None else None
        return FlowResponse(flow=self._flow.name, message=reply_payload, diagnostics=list(result.diagnostics))
