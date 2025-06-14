import random
import textwrap

from google.generativeai.types import HarmCategory, HarmBlockThreshold
from haystack import AsyncPipeline
from haystack_integrations.components.generators.google_ai import GoogleAIGeminiChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret
from naraninyeo.core.config import settings
from naraninyeo.models.message import MessageRequest

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
    }
)

async def generate_llm_response(message: MessageRequest) -> str:
    """
    LLM을 사용하여 사용자의 메시지에 대한 응답을 생성합니다.
    
    Args:
        message (str): 사용자의 입력 메시지
        
    Returns:
        str: 생성된 응답
    """
    messages = [
        ChatMessage.from_system(textwrap.dedent("""
            당신은 "나란잉여"라는 캐릭터입니다. 다음 특징을 가지고 있습니다:
            - 모든 질문에 대해 애매모호하고 중립적인 답변을 합니다
            - 단정적인 답변은 피하고 "그럴 수도 있고", "경우에 따라 다르다" 같은 표현을 자주 사용합니다
            - 친근하면서도 신중한 어조를 유지합니다
            - 답변은 1-2문장으로 간결하게 합니다
        """).strip()),
        ChatMessage.from_user(message.content)
        ]
    result = await generator.run_async(messages=messages)
    return result["replies"][0].text
