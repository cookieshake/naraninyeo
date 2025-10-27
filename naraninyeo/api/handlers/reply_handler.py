"""Flow that generates replies for existing messages on demand."""

from __future__ import annotations

from typing import Awaitable, Callable, Sequence

from naraninyeo.api.infrastructure.interfaces import MessageRepository
from naraninyeo.api.models import FlowResponse, MessageProcessingState, MessageResponse, ReplyRequest
from naraninyeo.core import BotReference, FlowBase, FlowContext, FlowExecutionResult, TaskBase, TenantReference

BotResolver = Callable[[TenantReference], Awaitable[BotReference | None]]


class ReplyGenerationFlow(
    FlowBase[MessageProcessingState, MessageProcessingState]
):  # pragma: no cover - orchestrates injected tasks
    def __init__(self, tasks: Sequence[TaskBase[FlowContext, MessageProcessingState, MessageProcessingState]]) -> None:
        super().__init__(tasks=list(tasks))


class ReplyHandler:
    def __init__(
        self,
        flow: ReplyGenerationFlow,
        repository: MessageRepository,
        *,
        resolve_bot: BotResolver | None = None,
    ) -> None:
        self._flow = flow
        self._repository = repository
        self._resolve_bot = resolve_bot

    async def handle(self, request: ReplyRequest) -> FlowResponse:
        tenant = TenantReference(tenant_id=request.tenant_id, bot_id=request.bot_id)
        source_message = await self._repository.get(tenant, request.channel_id, request.message_id)
        if source_message is None:
            raise LookupError(f"message {request.message_id} not found for tenant {tenant.as_key()}")
        bot = await self._resolve_bot(tenant) if self._resolve_bot else None
        metadata: dict[str, object] = {"tenant": tenant}
        if bot is not None:
            metadata["bot"] = bot
        context: FlowContext = self._flow.build_context(metadata=metadata)
        state = MessageProcessingState(tenant=tenant, bot=bot, inbound=source_message, stored=source_message)
        result: FlowExecutionResult[MessageProcessingState] = await self._flow.execute(context, state)
        reply = result.output.reply if result.output else None
        reply_payload = MessageResponse.from_domain(reply) if reply is not None else None
        return FlowResponse(flow=self._flow.name, message=reply_payload, diagnostics=list(result.diagnostics))
