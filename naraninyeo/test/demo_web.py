import uuid
from datetime import UTC, datetime

from httpx import Response
from shiny.express import ui

from naraninyeo.api.routers.bot import CreateBotRequest
from naraninyeo.api.routers.message import NewMessageRequest, NewMessageResponseChunk
from naraninyeo.core.models import Author, Channel, Message, MessageContent
from naraninyeo.test.conftest import _test_app, _test_client, _test_container

ui.page_opts(
    title="Hello Demo Chat",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=["Hello! How can I help you today?"],
)
chat.ui()

container = None
app = None
client = None
bot = None


@chat.on_user_submit
async def handle_user_input(user_input: str):
    global container, app, client, bot
    if container is None:
        container = await _test_container()
    if app is None:
        app = await _test_app(container)
    if client is None:
        client = _test_client(app)
    if bot is None:
        bot = CreateBotRequest(
            name="Test Bot",
            author_id="user_123"
        )
        response = client.post("/bots", content=bot.model_dump_json())
        bot = response.json()
    msg = NewMessageRequest(
        bot_id=bot["bot_id"],
        message=Message(
            message_id=uuid.uuid4().hex,
            channel=Channel(channel_id="channel_123", channel_name="text"),
            author=Author(author_id="user_456", author_name="Test User"),
            content=MessageContent(
                text=user_input,
                attachments=[],
            ),
            timestamp=datetime.now(UTC),
        ),
        reply_needed=True
    )
    response: Response = client.post("/new_message", content=msg.model_dump_json())
    if response.status_code != 200:
        msg = f"Unexpected status code: {response.status_code}, response: {response.text}"
        await chat.append_message(msg)
        raise AssertionError(msg)
    async for line in response.aiter_lines():
        res = NewMessageResponseChunk.model_validate_json(line)
        if res.generated_message:
            await chat.append_message(res.generated_message.content.text)
