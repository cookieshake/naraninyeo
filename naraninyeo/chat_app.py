import uuid
import gradio as gr
from typing import Tuple, List
from naraninyeo.models.message import Author, MessageRequest, MessageResponse
from naraninyeo.api.routes import handle_message
from naraninyeo.core.database import db

def respond(message: str, chat_history: List[Tuple[str, str]]) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Process message using HTTP requests to FastAPI server
    """
    try:
        request = MessageRequest(
            content=message,
            room="!!test!!",
            channelId="1234567890",
            author=Author(name="테스터"),
            isGroupChat=False,
            packageName="test",
            isDebugRoom=True,
            isMention=False,
            logId=str(uuid.uuid4()),
            isMultiChat=False,
        )
        
        response_data = handle_message(request)
        if response_data.do_reply:
            bot_message = response_data.message
        else:
            bot_message = "메시지가 저장되었습니다. (응답이 필요하지 않은 메시지입니다.)"
            
        chat_history.append((message, bot_message))
        return "", chat_history
    except Exception as e:
        error_message = f"오류가 발생했습니다: {str(e)}"
        chat_history.append((message, error_message))
        return "", chat_history

with gr.Blocks() as demo:
    gr.Markdown("# 나란잉여 채팅")
    chatbot = gr.Chatbot(type="tuples")
    msg = gr.Textbox(
        placeholder="메시지를 입력하세요...",
        label="메시지"
    )
    clear = gr.Button("대화 초기화")

    msg.submit(respond, [msg, chatbot], [msg, chatbot])
    clear.click(lambda: None, None, chatbot, queue=False)

if __name__ == "__main__":
    db.connect_to_database()
    demo.launch()

    