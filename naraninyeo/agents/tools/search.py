import html
import re
import httpx
from typing import Annotated, Literal

from naraninyeo.di import container
from naraninyeo.adapters.search_client import SearchClient

async def search_naver_api(
    query: str,
    category: Literal["news", "blog", "webkr", "encyc", "cafearticle", "doc"]
) -> str:
    """네이버 API를 통해 지정된 카테고리에서 정보를 검색합니다.
    
    다양한 카테고리(뉴스, 블로그, 웹문서, 백과사전, 카페글, 문서)에서 
    사용자가 입력한 쿼리에 맞는 정보를 검색하고 결과를 정형화된 문자열로 반환합니다.
    
    Args:
        query (str): 검색할 키워드 또는 문장
        category (Literal): 검색할 카테고리. 다음 중 하나여야 함:
            - "news": 뉴스 기사 검색
            - "blog": 블로그 글 검색
            - "webkr": 웹 문서 검색
            - "encyc": 백과사전 검색
            - "cafearticle": 카페 게시글 검색
            - "doc": 문서 검색
            
    Returns:
        str: 검색 결과를 포맷팅한 문자열. 각 결과는 제목, 설명, 날짜 정보를 포함합니다.
            결과가 없을 경우 "검색 결과가 없습니다."를 반환합니다.
            
    Raises:
        httpx.HTTPStatusError: API 호출 중 HTTP 오류가 발생한 경우
    
    Examples:
        >>> await search_naver_api("파이썬 프로그래밍", "blog")
        '제목: 파이썬 프로그래밍 시작하기\n설명: 파이썬 기초와 활용 방법...\n날짜: 2025-07-29\n\n제목: ...'
    """
    search_client = await container.get(SearchClient)
    try:
        response = await search_client.search(query, category, limit=5, sort="sim")
        if not response.items:
            return "검색 결과가 없습니다."
        results = []
        for item in response.items:
            date_info = f"\n날짜: {item.date}" if item.date else ""
            results.append(f"제목: {item.title}\n설명: {item.description}{date_info}\n")
        
        return "\n".join(results)
    except httpx.HTTPStatusError as e:
        return f"검색 중 오류가 발생했습니다: {e.response.status_code} - {e.response.text}"
