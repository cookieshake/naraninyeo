from datetime import datetime
from typing import Sequence

import pytest

from naraninyeo.api.handlers.message_handler import MessageHandler, MessageProcessingFlow
from naraninyeo.api.handlers.reply_handler import ReplyGenerationFlow, ReplyHandler
from naraninyeo.api.interfaces import (
    MemoryRepository,
    MemoryStrategy,
    MessageRepository,
    OutboundDispatcher,
    ReplyGenerator,
    WebSearchClient,
)
from naraninyeo.api.models import AuthorPayload, ChannelPayload, IncomingMessageRequest, ReplyRequest
from naraninyeo.api.tasks.generate_reply import GenerateReplyTask
from naraninyeo.api.tasks.get_history import GetHistoryTask
from naraninyeo.api.tasks.manage_memory import ManageMemoryTask
from naraninyeo.api.tasks.messages_to_memory import MessagesToMemoryTask
from naraninyeo.api.tasks.retrieve_memory import RetrieveMemoryTask
from naraninyeo.api.tasks.save_memory import SaveMemoryTask
from naraninyeo.api.tasks.search_history import SearchHistoryTask
from naraninyeo.api.tasks.search_web import SearchWebTask
from naraninyeo.api.tasks.store_message import StoreMessageTask
from naraninyeo.core import KnowledgeReference, MemoryItem, Message, MessageContent, RetrievalPlan


class InMemoryMessageRepository(MessageRepository):
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def save(self, message: Message) -> None:
        self.messages.append(message)

    async def history(self, tenant, channel_id: str, *, limit: int) -> Sequence[Message]:
        items = [msg for msg in self.messages if msg.tenant == tenant and msg.channel.channel_id == channel_id]
        return items[-limit:]

    async def history_after(self, tenant, channel_id: str, message_id: str, *, limit: int) -> Sequence[Message]:
        items = [msg for msg in self.messages if msg.tenant == tenant and msg.channel.channel_id == channel_id]
        index = next((i for i, m in enumerate(items) if m.message_id == message_id), len(items))
        return items[index + 1 : index + 1 + limit]

    async def search(self, tenant, channel_id: str, query: str, *, limit: int) -> Sequence[Message]:
        lowered = query.lower()
        return [
            msg
            for msg in self.messages
            if msg.tenant == tenant and msg.channel.channel_id == channel_id and lowered in msg.content.text.lower()
        ][:limit]

    async def get(self, tenant, channel_id: str, message_id: str) -> Message | None:
        for message in self.messages:
            matches_tenant = message.tenant == tenant
            matches_channel = message.channel.channel_id == channel_id
            matches_message = message.message_id == message_id
            if matches_tenant and matches_channel and matches_message:
                return message
        return None


class InMemoryMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self.items: list[MemoryItem] = []

    async def save_many(self, items: Sequence[MemoryItem]) -> None:
        self.items.extend(items)

    async def search(self, tenant, query: str, *, limit: int) -> Sequence[MemoryItem]:
        return [item for item in self.items if item.tenant == tenant][:limit]

    async def recent(self, tenant, channel_id: str, *, limit: int) -> Sequence[MemoryItem]:
        return [item for item in self.items if item.tenant == tenant and item.channel_id == channel_id][:limit]

    async def prune(self, tenant) -> None:
        self.items = [item for item in self.items if item.tenant == tenant and not item.is_expired]


class PassthroughMemoryStrategy(MemoryStrategy):
    async def prioritize(self, items: Sequence[MemoryItem]) -> Sequence[MemoryItem]:
        return items

    async def consolidate(self, items: Sequence[MemoryItem]) -> Sequence[MemoryItem]:
        return items


class StaticWebClient(WebSearchClient):
    async def search(self, plan: RetrievalPlan) -> Sequence[KnowledgeReference]:
        return [KnowledgeReference(content="doc", source_name="static", timestamp=datetime.utcnow())]


class EchoReplyGenerator(ReplyGenerator):
    async def generate(self, *, context) -> MessageContent:
        return MessageContent(text=f"Echo: {context.incoming.content.text}")


class CollectingDispatcher(OutboundDispatcher):
    def __init__(self) -> None:
        self.dispatched: list[Message] = []

    async def dispatch(self, message: Message) -> None:
        self.dispatched.append(message)


def build_tasks(repo: MessageRepository, mem_repo: MemoryRepository, dispatcher: CollectingDispatcher):
    return {
        "store": StoreMessageTask(repo),
        "history": GetHistoryTask(repo),
        "search_history": SearchHistoryTask(repo),
        "to_memory": MessagesToMemoryTask(),
        "save_memory": SaveMemoryTask(mem_repo),
        "manage_memory": ManageMemoryTask(mem_repo, PassthroughMemoryStrategy()),
        "retrieve_memory": RetrieveMemoryTask(mem_repo),
        "search_web": SearchWebTask(StaticWebClient()),
        "generate_reply": GenerateReplyTask(EchoReplyGenerator(), dispatcher),
    }


@pytest.mark.asyncio
async def test_message_flow_generates_reply():
    repo = InMemoryMessageRepository()
    mem_repo = InMemoryMemoryRepository()
    dispatcher = CollectingDispatcher()
    tasks = build_tasks(repo, mem_repo, dispatcher)

    flow = MessageProcessingFlow(
        [
            tasks["store"],
            tasks["history"],
            tasks["search_history"],
            tasks["to_memory"],
            tasks["save_memory"],
            tasks["manage_memory"],
            tasks["retrieve_memory"],
            tasks["search_web"],
            tasks["generate_reply"],
        ]
    )
    handler = MessageHandler(flow)

    payload = IncomingMessageRequest(
        tenant_id="tenant",
        bot_id="bot",
        channel=ChannelPayload(channel_id="channel", channel_name="Test"),
        author=AuthorPayload(author_id="user", display_name="User"),
        text="hello there",
        timestamp=datetime.utcnow(),
    )

    response = await handler.handle(payload)

    assert response.message is not None
    assert response.message.text.startswith("Echo:")
    assert dispatcher.dispatched, "Dispatcher should receive the generated reply"
    assert mem_repo.items, "Memory repository should store generated memories"


@pytest.mark.asyncio
async def test_reply_flow_uses_existing_message():
    repo = InMemoryMessageRepository()
    mem_repo = InMemoryMemoryRepository()
    dispatcher = CollectingDispatcher()
    tasks = build_tasks(repo, mem_repo, dispatcher)

    message_flow = MessageProcessingFlow(
        [
            tasks["store"],
            tasks["history"],
            tasks["search_history"],
            tasks["to_memory"],
            tasks["save_memory"],
            tasks["manage_memory"],
            tasks["retrieve_memory"],
            tasks["search_web"],
            tasks["generate_reply"],
        ]
    )
    message_handler = MessageHandler(message_flow)
    initial_request = IncomingMessageRequest(
        tenant_id="tenant",
        bot_id="bot",
        channel=ChannelPayload(channel_id="channel", channel_name="Test"),
        author=AuthorPayload(author_id="user", display_name="User"),
        text="need response",
        timestamp=datetime.utcnow(),
    )
    await message_handler.handle(initial_request)
    saved_message = repo.messages[0]

    reply_flow = ReplyGenerationFlow(
        [
            tasks["history"],
            tasks["search_history"],
            tasks["retrieve_memory"],
            tasks["search_web"],
            tasks["generate_reply"],
        ]
    )
    reply_handler = ReplyHandler(reply_flow, repo)
    reply_request = ReplyRequest(
        tenant_id="tenant",
        bot_id="bot",
        channel_id="channel",
        message_id=saved_message.message_id,
    )

    response = await reply_handler.handle(reply_request)
    assert response.message is not None
    assert response.message.text.startswith("Echo:")
