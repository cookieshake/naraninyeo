import asyncio
from datetime import datetime
from typing import AsyncIterator
from zoneinfo import ZoneInfo

import logfire

from naraninyeo.domain.model.message import Message
from naraninyeo.domain.model.reply import EnvironmentalContext, KnowledgeReference, ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalStatus
from naraninyeo.domain.usecase.message import MessageUseCase
from naraninyeo.domain.usecase.reply import ReplyUseCase
from naraninyeo.domain.usecase.retrieval import RetrievalUseCase


class NewMessageHandler:
    def __init__(
        self,
        message_use_case: MessageUseCase,
        retrieval_use_case: RetrievalUseCase,
        reply_use_case: ReplyUseCase
    ):
        self.message_use_case = message_use_case
        self.retrieval_use_case = retrieval_use_case
        self.reply_use_case = reply_use_case

    async def handle(self, message: Message) -> AsyncIterator[Message]:
        with logfire.span("NewMessageHandler.handle"):
            save_new_message_task = asyncio.create_task(self.message_use_case.save_message(message))

            if not await self.message_use_case.reply_needed(message):
                await save_new_message_task
                return

            reply_context = ReplyContext(
                environment=EnvironmentalContext(
                    timestamp=datetime.now(tz=ZoneInfo("Asia/Seoul")),
                    location="Seoul, Korea"
                ),
                last_message=message,
                latest_history=await self.message_use_case.get_recent_messages(message, limit=7),
                knowledge_references=[],
                processing_logs=[]
            )

            plans = await self.retrieval_use_case.plan_retrieval(reply_context)
            retrieval_results = await self.retrieval_use_case.execute_retrieval(plans, reply_context)
            reply_context.knowledge_references = [
                KnowledgeReference(
                    content=result.content,
                    source_name=result.source_name,
                    timestamp=result.source_timestamp
                )
                for result in retrieval_results
                if result.status == RetrievalStatus.SUCCESS
            ]
            async for reply in self.reply_use_case.create_replies(reply_context):
                yield reply
                await self.message_use_case.save_message(reply)
