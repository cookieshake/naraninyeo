import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import uvicorn
from shiny import reactive
from shiny.express import render, ui

from naraninyeo.api.routers.bot import CreateBotRequest
from naraninyeo.api.routers.message import NewMessageRequest, NewMessageResponseChunk
from naraninyeo.core.models import Author, Channel, Message, MessageContent
from naraninyeo.test.conftest import _test_app, _test_container

ui.page_opts(
    title="Hello Demo Chat",
    fillable=True,
    fillable_mobile=True,
)

rtest = reactive.Value("Empty")

with ui.layout_column_wrap():
    with ui.card():
        chat = ui.Chat(id="chat")
        chat.ui(messages=["Hello! How can I help you today?"])
    with ui.card():

        @render.code
        def display_test():
            return rtest()


container = None
app = None
client = None
bot_id = None
server_url = "http://127.0.0.1:32919"  # FastAPI 서버 주소
server_task = None


async def start_fastapi_server():
    """FastAPI 서버를 백그라운드에서 시작"""
    global container, app
    if container is None:
        container = await _test_container()
    if app is None:
        app = await _test_app(container)

    # uvicorn 설정
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=32919,
        log_level="warning",  # 로그 줄이기
    )
    server = uvicorn.Server(config)
    await server.serve()


@chat.on_user_submit  # pyright: ignore[reportPossiblyUnboundVariable]
async def handle_user_input(user_input: str):
    global container, app, client, bot_id, server_task, rtest

    # 첫 메시지일 때 서버 시작
    if server_task is None:
        await chat.append_message("서버를 시작합니다...")
        server_task = asyncio.create_task(start_fastapi_server())
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient() as _client:
                    await _client.get(server_url)
                break
            except Exception:
                continue
        await chat.append_message("서버가 시작되었습니다!")

    if client is None:
        # Create AsyncClient for HTTP requests to FastAPI server
        client = httpx.AsyncClient(base_url=server_url, timeout=httpx.Timeout(120.0))
    if bot_id is None:
        bot = CreateBotRequest(name="Test Bot", author_id="user_123")
        response = await client.post("/bots", content=bot.model_dump_json())
        bot = response.json()
        bot_id = bot["bot_id"]

    msg = NewMessageRequest(
        bot_id=bot_id,
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
        reply_needed=True,
    )
    try:
        async with client.stream(
            "POST", "/new_message", content=msg.model_dump_json(), headers={"Content-Type": "application/json"}
        ) as response:
            if response.status_code != 200:
                response_text = await response.aread()
                msg = f"Unexpected status code: {response.status_code}, response: {response_text.decode()}"
                await chat.append_message(msg)
                raise AssertionError(msg)

            async for line in response.aiter_lines():
                if line.strip():  # 빈 줄 무시
                    res = NewMessageResponseChunk.model_validate_json(line)
                    if res.generated_message:
                        await chat.append_message(res.generated_message.content.text)
                        rtest.set(res.model_dump_json(indent=2))
                        r = NewMessageRequest(
                            bot_id=bot_id,
                            message=Message(
                                message_id=uuid.uuid4().hex,
                                channel=Channel(channel_id="channel_123", channel_name="text"),
                                author=Author(author_id="user_123", author_name="Test Bot"),
                                content=MessageContent(
                                    text=res.generated_message.content.text,
                                    attachments=[],
                                ),
                                timestamp=datetime.now(UTC),
                            ),
                            reply_needed=False,
                        )
                        await client.post("/new_message", content=r.model_dump_json())
    except Exception as e:
        await chat.append_message(str(e))
