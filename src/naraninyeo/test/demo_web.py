import asyncio
import logging
import uuid
from datetime import UTC, datetime

import gradio as gr
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
_client = None
_bot_id: str | None = None


async def _ensure_server():
    global _container, _app, _server_task, _client, _bot_id

    if _server_task is not None and _client is not None and _bot_id is not None:
        return

    if _container is None:
        _container = await _test_container()
    if _app is None:
        _app = await _test_app(_container)

    logging.basicConfig(level=logging.INFO)
    config = uvicorn.Config(_app, host="127.0.0.1", port=32919, log_level="info")
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

    _client = httpx.AsyncClient(base_url=SERVER_URL, timeout=httpx.Timeout(120.0))
    bot_req = CreateBotRequest(name="Test Bot", author_id="user_123")
    response = await _client.post(
        "/bots", content=bot_req.model_dump_json(), headers={"Content-Type": "application/json"}
    )
    bot = response.json()
    _bot_id = bot["bot_id"]


async def chat(message: str, history: list):
    if not message.strip():
        yield history, None
        return

    await _ensure_server()

    assert _bot_id is not None
    msg_req = NewMessageRequest(
        bot_id=_bot_id,
        message=Message(
            message_id=uuid.uuid4().hex,
            channel=Channel(channel_id="channel_123", channel_name="text"),
            author=Author(author_id="user_456", author_name="Test User"),
            content=MessageContent(text=message, attachments=[]),
            timestamp=datetime.now(UTC),
        ),
        reply_needed=True,
    )

    history = history + [{"role": "user", "content": message}]
    last_chunk_json = None
    bot_texts: list[str] = []

    try:
        async with _client.stream(  # type: ignore[union-attr]
            "POST", "/new_message", content=msg_req.model_dump_json(), headers={"Content-Type": "application/json"}
        ) as response:
            if response.status_code != 200:
                response_text = await response.aread()
                err = f"Unexpected status code: {response.status_code}, response: {response_text.decode()}"
                history.append({"role": "assistant", "content": err})
                yield history, None
                return

            async for line in response.aiter_lines():
                if line.strip():
                    res = NewMessageResponseChunk.model_validate_json(line)
                    if res.generated_message:
                        bot_texts.append(res.generated_message.content.text)
                        current_history = history + [{"role": "assistant", "content": t} for t in bot_texts]
                        last_chunk_json = res.model_dump()
                        yield current_history, last_chunk_json

        history = history + [{"role": "assistant", "content": t} for t in bot_texts]
        full_text = "\n".join(bot_texts)
        if full_text:
            assert _bot_id is not None
            echo = NewMessageRequest(
                bot_id=_bot_id,
                message=Message(
                    message_id=uuid.uuid4().hex,
                    channel=Channel(channel_id="channel_123", channel_name="text"),
                    author=Author(author_id="user_123", author_name="Test Bot"),
                    content=MessageContent(text=full_text, attachments=[]),
                    timestamp=datetime.now(UTC),
                ),
                reply_needed=False,
            )
            await _client.post("/new_message", content=echo.model_dump_json())  # type: ignore[union-attr]

    except Exception as e:
        history.append({"role": "assistant", "content": str(e)})
        yield history, last_chunk_json


with gr.Blocks(title="나란이녀 Demo") as demo:
    chatbot = gr.Chatbot(label="Chat")
    pending_msg = gr.State("")
    with gr.Row():
        txt = gr.Textbox(show_label=False, placeholder="메시지를 입력하세요...", scale=8)
        send_btn = gr.Button("전송", scale=1)
    with gr.Accordion("Debug", open=False):
        debug_json = gr.JSON(label="Last Response Chunk")

    def prepare(message):
        return "", message

    txt.submit(fn=prepare, inputs=[txt], outputs=[txt, pending_msg]).then(
        fn=chat, inputs=[pending_msg, chatbot], outputs=[chatbot, debug_json]
    )
    send_btn.click(fn=prepare, inputs=[txt], outputs=[txt, pending_msg]).then(
        fn=chat, inputs=[pending_msg, chatbot], outputs=[chatbot, debug_json]
    )

if __name__ == "__main__":
    demo.launch()
