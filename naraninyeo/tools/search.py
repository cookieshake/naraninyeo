import html
import re
import httpx
from typing import Annotated, Literal
from agno.tools import tool

from naraninyeo.core.config import settings

async def _search_naver_api(query: str, limit: int, sort: Literal["sim", "date"], api_name: Literal["news", "blog", "webkr"]) -> dict[str, str]:
    url = f"https://openapi.naver.com/v1/search/{api_name}.json"
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET
    }
    params = {
        "query": query,
        "display": limit,
        "sort": sort
    }
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, params=params)
        res = res.json()
    items = [
        {"title": i['title'], "description": i['description']}
        for i in res["items"]
    ]
    for i in items:
        i["title"] = re.sub(r"</?b>", "", i["title"])
        i["description"] = re.sub(r"</?b>", "", i["description"])
        i["description"] = html.unescape(i["description"])
    return items

@tool(show_result=True)
async def search_naver_news(
    query: str,
    limit: int = 15,
    sort_by_date: bool = False
) -> str:
    """
    Search for news articles using the Naver API.
    
    Args:
        query: The query to search for
        limit: The number of news to return. (default: 15)
        sort_by_date: Whether to sort by most recent date first. (default: False)
    """
    sort = "date" if sort_by_date else "sim"
    items = await _search_naver_api(query, limit, sort, "news")
    result = ""
    for i in items:
        result += f"title: {i['title']}\\n"
        result += f"description: {i['description']}\\n"
        result += "\\n"
    return result

@tool(show_result=True)
async def search_naver_blog(
    query: str,
    limit: int = 15,
    sort_by_date: bool = False
) -> str:
    """
    Search for blog articles using the Naver API.
    
    Args:
        query: The query to search for
        limit: The number of blogs to return. (default: 15)
        sort_by_date: Whether to sort by most recent date first. (default: False)
    """
    sort = "date" if sort_by_date else "sim"
    items = await _search_naver_api(query, limit, sort, "blog")
    result = ""
    for i in items:
        result += f"title: {i['title']}\\n"
        result += f"description: {i['description']}\\n"
        result += "\\n"
    return result

@tool(show_result=True)
async def search_naver_web(
    query: str,
    limit: int = 15,
    sort_by_date: bool = False
) -> str:
    """
    Search for web pages using the Naver API.
    
    Args:
        query: The query to search for
        limit: The number of web pages to return. (default: 15)
        sort_by_date: Whether to sort by most recent date first. (default: False)
    """
    sort = "date" if sort_by_date else "sim"
    items = await _search_naver_api(query, limit, sort, "webkr")
    result = ""
    for i in items:
        result += f"title: {i['title']}\\n"
        result += f"description: {i['description']}\\n"
        result += "\\n"
    return result