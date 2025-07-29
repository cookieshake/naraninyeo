"""LLM 관련 데이터 모델 정의"""

from typing import Literal
from pydantic import BaseModel, Field, field_validator

from naraninyeo.core.config import settings

class TeamResponse(BaseModel):
    """팀 응답 모델"""
    response: str = Field(description="나란잉여의 응답")
    is_final: bool = Field(description="마지막 답변인지 여부")

class SearchMethod(BaseModel):
    """검색 방법 모델"""
    type: Literal["news", "blog", "web", "encyclopedia", "cafe", "doc"] = Field(description="검색 유형")
    query: str = Field(description="검색어")
    limit: int = Field(default=settings.DEFAULT_SEARCH_LIMIT, description="결과 수")
    sort: Literal["sim", "date"] = Field(default="sim", description="정렬 방식")

class SearchPlan(BaseModel):
    """검색 계획 모델"""
    methods: list[SearchMethod] = Field(description="수행할 검색 목록")

    @field_validator('methods')
    def methods_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("하나 이상의 검색 방법이 필요합니다.")
        return v

