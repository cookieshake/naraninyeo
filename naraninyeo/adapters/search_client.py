"""검색 관련 클라이언트 - 외부 검색 API 래핑"""

import html
import re
import httpx
from typing import List, Literal, Optional, Dict, Any
from datetime import datetime

from opentelemetry import trace
from pydantic import BaseModel, Field
from naraninyeo.core.config import Settings

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


class SearchClient:
    """검색 클라이언트 - 네이버 검색 API 사용"""

    def __init__(self, settings: Settings):
        self.client_id = settings.NAVER_CLIENT_ID
        self.client_secret = settings.NAVER_CLIENT_SECRET
    
    @tracer.start_as_current_span("search")
    async def search(self, query: str, search_type: str, limit: int = 5, sort: str = "sim") -> SearchResponse:
        """검색 수행
        
        Args:
            query (str): 검색어
            search_type (str): 검색 타입 ('news', 'blog', 'web', 'encyclopedia', 'cafe', 'doc')
            limit (int): 검색 결과 수
            sort (str): 정렬 방식. 'sim'은 정확도순, 'date'는 날짜순
            
        Returns:
            SearchResponse: 검색 결과
        """
        span = trace.get_current_span()
        
        # 검색 타입에 따른 API 이름 매핑
        api_name_map = {
            "news": "news",
            "blog": "blog",
            "web": "webkr",
            "encyclopedia": "encyc",
            "cafe": "cafearticle",
            "doc": "doc"
        }
        
        api_name = api_name_map.get(search_type)
        if not api_name:
            raise ValueError(f"Unsupported search type: {search_type}")
        
        url = f"https://openapi.naver.com/v1/search/{api_name}.json"
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }
        params = {"query": query, "display": limit, "sort": sort}
        
        span.set_attribute("query", query)
        span.set_attribute("search_type", search_type)
        span.set_attribute("api_name", api_name)
        span.set_attribute("params", params)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            data = response.json()
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
