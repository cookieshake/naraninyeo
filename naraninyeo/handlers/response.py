import random
import textwrap
from zoneinfo import ZoneInfo

from google.generativeai.types import HarmCategory, HarmBlockThreshold
from haystack import AsyncPipeline
from haystack.components.tools import ToolInvoker
from haystack_integrations.components.generators.google_ai import GoogleAIGeminiChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret
from naraninyeo.core.config import settings
from naraninyeo.handlers.history import get_history
from naraninyeo.models.message import MessageRequest
from naraninyeo.tools import default_toolset

RANDOM_RESPONSES = [
    "음… 그렇게 볼 수도 있겠네요.",
    "사람마다 다를 수 있죠, 뭐.",
    "그럴 만도 하네요, 듣고 보니.",
    "그런 얘기, 종종 들려요.",
    "뭐, 그런 식으로도 생각할 수 있죠.",
    "그럴 수도 있고 아닐 수도 있겠네요. 알 수 없는 거죠.",
    "세상엔 참 다양한 생각이 있는 것 같아요.",
    "맞다기보단… 그냥 그런 경우도 있는 거 같아요.",
    "그런 입장도 충분히 이해는 가요.",
    "어떻게 보면 맞는 말이죠, 생각하기 나름이에요.",
    "그런 관점도 있군요, 흥미롭네요.",
    "사실 정답은 없는 것 같아요.",
    "그럴 법도 하네요, 충분히.",
    "음, 나름대로의 이유가 있겠죠.",
    "그런 식으로 접근하는 것도 방법이네요.",
    "뭐라고 딱 잘라 말하기는 어렵겠어요.",
    "경우에 따라 다를 수 있겠네요.",
    "그런 시각으로 보면 그렇겠어요.",
    "일리가 있는 말씀이에요.",
    "그럴 가능성도 배제할 수는 없죠.",
    "상황에 따라서는 맞는 말일 수도 있어요.",
    "그런 해석도 가능하겠네요.",
    "어느 정도는 공감이 가는 부분이에요.",
    "그런 각도에서 보면 그럴 수도 있고요.",
    "사람들이 흔히 하는 얘기죠.",
    "그런 면도 분명히 있을 거예요.",
    "완전히 틀렸다고는 할 수 없겠네요.",
    "그런 생각을 하는 사람들도 많죠.",
    "어떻게 보느냐에 따라 달라지는 것 같아요.",
    "그런 입장에서는 당연한 생각이겠어요.",
    "뭐, 그럴 수도 있는 일이죠.",
    "그런 관점에서는 이해가 가네요.",
    "상당히 설득력 있는 의견이에요.",
    "그런 측면도 고려해볼 만하네요.",
    "충분히 그럴 만한 이유가 있겠어요.",
    "그런 식으로 생각해본 적은 없었는데, 흥미롭네요.",
    "케이스 바이 케이스인 것 같아요.",
    "그런 부분도 무시할 수는 없죠.",
    "어느 정도 타당성이 있는 말씀이에요.",
    "그런 시선으로 바라보면 그렇겠네요."
]

def get_random_response(message: MessageRequest) -> str:
    """
    Get a random response from the predefined list
    """
    rand = random.Random(message.content)
    return rand.choice(RANDOM_RESPONSES) 


# Initialize the generator and pipeline
generator = GoogleAIGeminiChatGenerator(
    api_key=Secret.from_token(settings.GOOGLE_API_KEY),
    model="gemini-2.5-flash-preview-05-20",
    generation_config={
        "candidate_count": 1
    },
    safety_settings={
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE
    },
    tools=default_toolset
)

tool_invoker = ToolInvoker(
    tools=default_toolset
)

async def generate_llm_response(message: MessageRequest) -> str:
    """
    LLM을 사용하여 사용자의 메시지에 대한 응답을 생성합니다.
    
    Args:
        message (str): 사용자의 입력 메시지
        
    Returns:
        str: 생성된 응답
    """

    history = await get_history(message.room_id, message.created_at, 15)
    history.append(message)
    history_str = ""
    for h in history:
        history_str += f"{h.created_at.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")} {h.sender} : {h.content}\n"
        if h.has_response:
            history_str += f"{h.created_at.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S")} 나란잉여 : {h.response}\n"
    history_str = textwrap.dedent(history_str).strip()

    messages = [
        ChatMessage.from_system(textwrap.dedent("""
            당신은 똑똑한 채팅봇 '나란잉여' 입니다.  
            - 다양한 주제에 대해 논리적이고 균형 잡힌 사고를 유도하며, 사용자가 스스로 비판적으로 사고할 수 있도록 돕습니다  
            - 특정 이념이나 감정에 치우치지 않고, 다양한 관점을 존중하며 사실과 근거를 바탕으로 대화합니다.  
            - 사용자가 편향된 주장을 할 경우, “이 주장의 근거는 무엇인가요?”, “다른 시각은 어떤 것이 있을까요?” 등의 질문을 통해 사고를 확장하도록 유도합니다.  
            - 필요한 경우에는 공신력 있는 자료와 구체적 데이터를 바탕으로 설명하거나 반박합니다. 출처에는 날짜와 기관을 함께 명시합니다.  
            - 모든 대화에서 친절하고 예의 있는 태도를 유지하며, 차별·혐오·폭력적 표현은 사용하지 않습니다.  
            - 오류가 있거나 부족한 설명이 있을 경우, 이를 인정하고 수정합니다.  
            - 당신은 여러 사람이 참여한 대화방에 있으며, 흐름을 파악하고 맥락에 맞게 발언합니다.
            - 간결하고 정중한 표현을 사용하세요.
            - 중립적이며 친근하게 대화를 이끌고, 특정 사람의 의견이나 감정을 무시하거나 강조하지 않도록 주의합니다.
	•	 - 대화를 더욱 생산적으로 만든다는 목적과 참여자들의 협업과 소통을 돕도록 대답합니다.
	•	 - 새로운 안건이나 갈등이 발생하거나 협의해야 할 문제가 있을 때 공정하게 중재하거나 요약합니다.
	•	 - 강조하거나 개입해야 할 대화를 인지했을 때 주제를 요약하거나 투명하게 전달합니다.
            - 대화를 더욱 긍정적, 협력적으로 이끌고, 사람들끼리 더욱 깊고 원만하게 소통할 수 있도록 돕는 역할이라는 점을 기억해주세요.
        """).strip()),
        ChatMessage.from_user(textwrap.dedent(f"""\
            아래는 당신이 속한 채팅방의 대화의 기록입니다.
            
            {history_str}

            이 대화 기록 바로 다음에 '나란잉여'가 할 말을 작성해주세요. 다른 아무 말도 하지 마세요.
        """).strip())
        ]
    replies = (await generator.run_async(messages=messages))["replies"]
    if replies[0].tool_calls:
        tool_messages = await tool_invoker.run_async(replies[0].tool_calls)
        replies = (await generator.run_async(messages=messages + replies + tool_messages))["replies"]
    return replies[0].text

