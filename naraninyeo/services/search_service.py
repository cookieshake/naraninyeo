import html
import re
import httpx
from typing import List, Literal, Optional
from datetime import datetime

from opentelemetry import trace
from pydantic import BaseModel, Field
from naraninyeo.core.config import settings

tracer = trace.get_tracer(__name__)

class SearchItem(BaseModel):
    """검색 결과 아이템"""
    title: str = Field(description="검색 결과 제목")
    description: str = Field(description="검색 결과 설명")
    link: str = Field(description="검색 결과 링크")
    date: Optional[str] = Field(None, description="검색 결과 날짜")
    source: str = Field(description="검색 결과 소스 (ex: 네이버)")
    source_type: str = Field(description="검색 결과 타입 (ex: 뉴스, 블로그)")


class SearchResponse(BaseModel):
    """검색 응답"""
    query: str = Field(description="검색어")
    items: List[SearchItem] = Field(default_factory=list, description="검색 결과 목록")

@tracer.start_as_current_span("search_naver_api")
async def search_naver_api(
    query: str,
    limit: int,
    sort: Literal["sim", "date"],
    api_name: Literal["news", "blog", "webkr", "encyc", "cafearticle", "doc"],
) -> SearchResponse:
    """네이버 검색 API를 호출하여 검색 결과를 가져옵니다.

    Args:
        query (str): 검색어
        limit (int): 검색 결과 수
        sort (Literal["sim", "date"]): 정렬 방식. 'sim'은 정확도순, 'date'는 날짜순
        api_name (Literal["news", "blog", "webkr", "encyc", "cafearticle", "doc"]): 네이버 검색 API 타입
            - "news": 뉴스 검색
            - "blog": 블로그 검색
            - "webkr": 웹 페이지 검색
            - "encyc": 백과사전 검색
            - "cafearticle": 네이버 카페 게시글 검색
            - "doc": 전문 문서 검색

    Returns:
        SearchResponse: 검색 결과
    """
    span = trace.get_current_span()

    url = f"https://openapi.naver.com/v1/search/{api_name}.json"
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET
    }
    params = {"query": query, "display": limit, "sort": sort}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        data = response.json()
        span.set_attribute("search_type", api_name)
        span.set_attribute("params", params)
        span.set_attribute("response_status", response.status_code)
        span.set_attribute("response_data", data)

    # API 응답 타입에 따른 소스 타입 매핑
    source_type_map = {
        "news": "뉴스",
        "blog": "블로그",
        "webkr": "웹",
        "encyc": "백과사전",
        "cafearticle": "카페",
        "doc": "전문자료"
    }
    
    source_type = source_type_map.get(api_name, api_name)
    items = []
    
    for item in data.get("items", []):
        # HTML 태그 제거 및 특수문자 이스케이프 해제
        title = re.sub(r"</?b>", "", item.get("title", ""))
        description = re.sub(r"</?b>", "", item.get("description", ""))
        description = html.unescape(description)
        
        # 날짜 필드는 API마다 다를 수 있음
        date = item.get("pubDate") or item.get("postdate", "")
        
        items.append(
            SearchItem(
                title=title,
                description=description,
                link=item.get("link", ""),
                date=date,
                source="네이버",
                source_type=source_type
            )
        )
    
    return SearchResponse(
        query=query,
        items=items
    )



