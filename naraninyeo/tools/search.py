import html
import re
import httpx
from typing import Annotated, Literal
from agno.tools import tool

from naraninyeo.core.config import settings

@tool(show_result=True)
async def search_naver_api(
    query: str,
    limit: int,
    sort: Literal["sim", "date"],
    api_name: Literal["news", "blog", "webkr", "encyc", "cafearticle", "doc"]
) -> str:
    """Fetches various search results by calling the Naver Search API.

    Args:
        query (str): The string to search for.
        limit (int): The number of search results to return.
        sort (Literal["sim", "date"]): The sorting option. 'sim' for accuracy, 'date' for recency.
        api_name (Literal["news", "blog", "webkr", "encyc", "cafearticle", "local", "doc"]): The type of Naver Search API to use.
            - "news": News search.
            - "blog": Blog search.
            - "webkr": Web page search.
            - "encyc": Encyclopedia search.
            - "cafearticle": Naver Cafe article search.
            - "doc": Specialized document search.

    Returns:
        str: A formatted string summarizing the search results, including title, description, and date for each item.
    """
    url = f"https://openapi.naver.com/v1/search/{api_name}.json"
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET
    }
    params = {"query": query, "display": limit, "sort": sort}
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, params=params)
        res = res.json()

    items = res.get("items", [])
    if not items:
        return "No search results found."

    for i in items:
        i["title"] = re.sub(r"</?b>", "", i["title"])
        i["description"] = re.sub(r"</?b>", "", i["description"])
        i["description"] = html.unescape(i["description"])
        # The date field name differs for each API (news: pubDate, blog: postdate).
        i["date"] = i.get("pubDate") or i.get("postdate", "")

    result = ""
    for i in items:
        result += f"title: {i['title']}\n"
        result += f"description: {i['description']}\n"
        if i.get("date"):
            result += f"date: {i['date']}\n"
        result += "\n"
    return result.strip()
