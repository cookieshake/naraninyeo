"""랜덤 응답 서비스"""

import random
from typing import List

class RandomResponderService:
    """랜덤 응답 생성 서비스
    
    단순히 미리 정의된 응답 목록에서 랜덤하게 하나를 선택하여 제공합니다.
    """
    
    # 클래스 변수로 응답 목록 정의
    RANDOM_RESPONSES: List[str] = [
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
        "음, 그럴 수도 있겠어요.",
        "그렇게 생각해본 적은 없었는데, 흥미로운 관점이네요.",
        "뭐, 다양한 의견이 있을 수 있죠.",
        "상황에 따라 달라질 수 있는 문제 같아요."
    ]
    
    def __init__(self):
        """초기화 - 빈 생성자로 변경"""
        pass
    
    @classmethod
    def get_random_response(cls) -> str:
        """랜덤 응답 텍스트 반환
        
        단순히 미리 정의된 응답 목록에서 랜덤하게 하나를 선택하여 반환합니다.
        
        Returns:
            str: 랜덤하게 선택된 응답 문자열
        """
        return random.choice(cls.RANDOM_RESPONSES)
