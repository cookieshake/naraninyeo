import html
import re
import httpx
from typing import Annotated, Literal
from datetime import datetime
from zoneinfo import ZoneInfo
from haystack.tools import tool

from naraninyeo.core.config import settings

async def _search_naver_api(query: str, limit: int, api_name: Literal["news", "blog", "webkr"]) -> dict[str, str]:
    url = f"https://openapi.naver.com/v1/search/{api_name}.json"
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET
    }
    params = {
        "query": query,
        "display": limit
    }
    async with httpx.AsyncClient() as client:
        res = (await client.get(url, headers=headers, params=params)).json()
    items = [
        {"title": i['title'], "description": i['description']}
        for i in res["items"]
    ]
    for i in items:
        i["title"] = re.sub(r"</?b>", "", i["title"])
        i["description"] = re.sub(r"</?b>", "", i["description"])
        i["description"] = html.unescape(i["description"])
    return items

@tool
async def search_naver_news(
    query: Annotated[str, "The query to search for"],
    limit: Annotated[int, "The number of news to return. (default: 15)"] = 15
) -> str:
    """
    Search for news articles using the Naver API.
    """
    items = await _search_naver_api(query, limit, "news")
    result = ""
    for i in items:
        result += f"- title: {i['title']}\n"
        result += f"  description: {i['description']}\n"
    return result

@tool
async def search_naver_blog(
    query: Annotated[str, "The query to search for"],
    limit: Annotated[int, "The number of blogs to return. (default: 15)"] = 15
) -> str:
    """
    Search for blog articles using the Naver API.
    """
    items = await _search_naver_api(query, limit, "blog")
    result = ""
    for i in items:
        result += f"- title: {i['title']}\n"
        result += f"  description: {i['description']}\n"
    return result

@tool
async def search_naver_webkr(
    query: Annotated[str, "The query to search for"],
    limit: Annotated[int, "The number of web articles to return. (default: 15)"] = 15
) -> str:
    """
    Search for web articles using the Naver API.
    """
    items = await _search_naver_api(query, limit, "webkr")
    result = ""
    for i in items:
        result += f"- title: {i['title']}\n"
        result += f"  description: {i['description']}\n"
    return result