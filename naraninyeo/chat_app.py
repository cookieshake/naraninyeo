import uuid
import gradio as gr
import subprocess
import requests
import time
import threading
import sys
from typing import Tuple, List
from naraninyeo.models.message import Author, MessageRequest, MessageResponse

# FastAPI 서버 URL
SERVER_URL = "http://localhost:8000"

def log_output(pipe, prefix):
    """Log output from subprocess pipe"""
    for line in iter(pipe.readline, b''):
        print(f"{prefix}: {line.strip()}")
    pipe.close()

def start_server():
    """Start FastAPI server in a subprocess"""
    process = subprocess.Popen(
        ["uvicorn", "naraninyeo.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
        universal_newlines=True
    )
    
    # 로그 출력을 위한 스레드 시작
    threading.Thread(target=log_output, args=(process.stdout, "SERVER"), daemon=True).start()
    threading.Thread(target=log_output, args=(process.stderr, "ERROR"), daemon=True).start()
    
    # 서버가 시작될 때까지 잠시 대기
    time.sleep(2)
    return process

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
        
        response = requests.post(f"{SERVER_URL}/new_message", json=request.model_dump())
        response_data = MessageResponse.model_validate(response.json())
        
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

# FastAPI 서버 시작
server_process = start_server()

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
    try:
        demo.launch()
    finally:
        # 프로그램 종료 시 서버 프로세스 정리
        server_process.terminate()
        server_process.wait() 
    