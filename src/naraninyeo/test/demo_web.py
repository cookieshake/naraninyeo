import asyncio
import uuid
from datetime import UTC, datetime

import chainlit as cl
import httpx
import uvicorn

from naraninyeo.api.routers.bot import CreateBotRequest
from naraninyeo.api.routers.message import NewMessageRequest, NewMessageResponseChunk
from naraninyeo.conftest import _test_app, _test_container
from naraninyeo.core.models import Author, Channel, Message, MessageContent

SERVER_URL = "http://127.0.0.1:32919"

_container = None
_app = None
_server_task = None


async def _ensure_server():
    global _container, _app, _server_task

    if _server_task is not None:
        return

    if _container is None:
        _container = await _test_container()
    if _app is None:
        _app = await _test_app(_container)

    config = uvicorn.Config(_app, host="127.0.0.1", port=32919, log_level="warning")
    server = uvicorn.Server(config)
    _server_task = asyncio.create_task(server.serve())

    for _ in range(30):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient() as c:
                await c.get(SERVER_URL)
            break
        except Exception:
            continue


@cl.on_chat_start
async def on_chat_start():
    async with cl.Step(name="서버 초기화") as step:
        step.output = "testcontainers 시작 중..."
        async with cl.Step(name="Step 1: testcontainers"):
            global _container
            if _container is None:
                _container = await _test_container()

        async with cl.Step(name="Step 2: FastAPI 앱 생성"):
            global _app
            if _app is None:
                _app = await _test_app(_container)

        async with cl.Step(name="Step 3: uvicorn 서버 기동") as s3:
            global _server_task
            if _server_task is None:
                config = uvicorn.Config(_app, host="127.0.0.1", port=32919, log_level="warning")
                server = uvicorn.Server(config)
                _server_task = asyncio.create_task(server.serve())
                for _ in range(30):
                    await asyncio.sleep(1)
                    try:
                        async with httpx.AsyncClient() as c:
                            await c.get(SERVER_URL)
                        break
                    except Exception:
                        continue
            s3.output = "서버 준비 완료"

        async with cl.Step(name="Step 4: 봇 생성") as s4:
            client = httpx.AsyncClient(base_url=SERVER_URL, timeout=httpx.Timeout(120.0))
            bot_req = CreateBotRequest(name="Test Bot", author_id="user_123")
            response = await client.post("/bots", content=bot_req.model_dump_json())
            bot = response.json()
            bot_id = bot["bot_id"]
            cl.user_session.set("client", client)
            cl.user_session.set("bot_id", bot_id)
            s4.output = f"봇 생성 완료: {bot_id}"

        step.output = "초기화 완료"

    await cl.Message(content="안녕하세요! 무엇을 도와드릴까요?").send()


@cl.on_message
async def on_message(message: cl.Message):
    client: httpx.AsyncClient = cl.user_session.get("client")
    bot_id: str = cl.user_session.get("bot_id")

    msg_req = NewMessageRequest(
        bot_id=bot_id,
        message=Message(
            message_id=uuid.uuid4().hex,
            channel=Channel(channel_id="channel_123", channel_name="text"),
            author=Author(author_id="user_456", author_name="Test User"),
            content=MessageContent(text=message.content, attachments=[]),
            timestamp=datetime.now(UTC),
        ),
        reply_needed=True,
    )

    reply = cl.Message(content="")
    await reply.send()

    try:
        async with client.stream(
            "POST", "/new_message", content=msg_req.model_dump_json(), headers={"Content-Type": "application/json"}
        ) as response:
            if response.status_code != 200:
                response_text = await response.aread()
                err = f"Unexpected status code: {response.status_code}, response: {response_text.decode()}"
                await reply.update()
                raise AssertionError(err)

            full_text = ""
            async for line in response.aiter_lines():
                if line.strip():
                    res = NewMessageResponseChunk.model_validate_json(line)
                    if res.generated_message:
                        full_text = res.generated_message.content.text
                        reply.content = full_text
                        await reply.update()

                        echo = NewMessageRequest(
                            bot_id=bot_id,
                            message=Message(
                                message_id=uuid.uuid4().hex,
                                channel=Channel(channel_id="channel_123", channel_name="text"),
                                author=Author(author_id="user_123", author_name="Test Bot"),
                                content=MessageContent(text=full_text, attachments=[]),
                                timestamp=datetime.now(UTC),
                            ),
                            reply_needed=False,
                        )
                        await client.post("/new_message", content=echo.model_dump_json())
    except Exception as e:
        reply.content = str(e)
        await reply.update()
