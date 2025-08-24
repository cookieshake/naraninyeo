from typing import AsyncIterator

from naraninyeo.domain.gateway.reply import ReplyGenerator
from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import ReplyContext


class ReplyUseCase:
    def __init__(self, reply_generator: ReplyGenerator):
        self.reply_generator = reply_generator

    async def create_replies(self, context: ReplyContext) -> AsyncIterator[Message]:
        async for reply in self.reply_generator.generate_reply(context):  # type: ignore
            yield reply
