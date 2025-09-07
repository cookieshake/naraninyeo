from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Sequence

from naraninyeo.core.middleware import ChatMiddleware
from naraninyeo.core.pipeline.steps import StepRegistry
from naraninyeo.core.pipeline.types import PipelineState
from naraninyeo.domain.gateway.message import MessageRepository
from naraninyeo.domain.model.message import Message
from naraninyeo.infrastructure.settings import Settings


class PipelineRunner:
    """Runs a configured sequence of steps and streams replies via an async iterator."""

    def __init__(
        self,
        settings: Settings,
        message_repository: MessageRepository,
        step_registry: StepRegistry,
        step_order: Sequence[str],
        middlewares: list[ChatMiddleware] | None = None,
    ) -> None:
        self.settings = settings
        self.message_repository = message_repository
        self.step_registry = step_registry
        self.step_order = list(step_order)
        self._middlewares = middlewares or []

    async def run(self, message: Message) -> AsyncIterator[Message]:  # type: ignore[override]
        # Call middleware hook
        for mw in self._middlewares:
            await mw.before_handle(message)

        queue: asyncio.Queue[Message] = asyncio.Queue()
        state = PipelineState(incoming=message)

        async def emit(reply: Message) -> None:
            # Enqueue for streaming; saving and on_reply will occur after the item is yielded
            await queue.put(reply)

        # Producer: run steps sequentially
        producer_done = asyncio.Event()

        async def produce():
            try:
                for name in self.step_order:
                    step = self.step_registry.get(name)
                    await step.run(state, emit)
                    if state.stop:
                        break
            finally:
                producer_done.set()

        producer_task = asyncio.create_task(produce())

        # Consumer: stream until producer finishes and queue drains
        try:
            while True:
                if producer_done.is_set() and queue.empty():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.05)
                    # Stream to caller first (preserve original behavior)
                    yield item
                    # After yielding, persist and notify middleware
                    await self.message_repository.save(item)
                    for mw in self._middlewares:
                        await mw.on_reply(item)
                except asyncio.TimeoutError:
                    continue
        finally:
            # Ensure producer completed
            await producer_task
            # Run finalizers added by steps (saving, background tasks, etc.)
            if state.finalizers:
                await asyncio.gather(*state.finalizers, return_exceptions=True)
