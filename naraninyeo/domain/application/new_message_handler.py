from typing import AsyncIterator

from opentelemetry.trace import get_tracer

from naraninyeo.core.pipeline.runner import PipelineRunner
from naraninyeo.domain.model.message import Message


class NewMessageHandler:
    def __init__(self, pipeline_runner: PipelineRunner):
        self._runner = pipeline_runner

    async def handle(self, message: Message) -> AsyncIterator[Message]:
        with get_tracer(__name__).start_as_current_span("handle new message"):
            async for reply in self._runner.run(message):
                yield reply
