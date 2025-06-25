import html
import re
import httpx
from typing import Annotated, Literal
from agno.tools import tool

from naraninyeo.core.config import settings

def _search_naver_api(query: str, limit: int, sort: Literal["sim", "date"], api_name: Literal["news", "blog", "webkr"]) -> dict[str, str]:
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
    with httpx.Client() as client:
        res = client.get(url, headers=headers, params=params).json()
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
def search_naver_news(
    query: Annotated[str, "The query to search for"],
    limit: Annotated[int, "The number of news to return. (default: 15)"] = 15,
    sort: Annotated[Literal["sim", "date"], "The sort order of the news. 'sim' sorts by highest similarity first, 'date' sorts by most recent date first."] = "sim"
) -> str:
    """
    Search for news articles using the Naver API.
    """
    items = _search_naver_api(query, limit, sort, "news")
    result = ""
    for i in items:
        result += f"title: {i['title']}\\n"
        result += f"description: {i['description']}\\n"
        result += "\\n"
    return result

@tool(show_result=True)
def search_naver_blog(
    query: Annotated[str, "The query to search for"],
    limit: Annotated[int, "The number of blogs to return. (default: 15)"] = 15,
    sort: Annotated[Literal["sim", "date"], "The sort order of the blogs. 'sim' sorts by highest similarity first, 'date' sorts by most recent date first."] = "sim"
) -> str:
    """
    Search for blog articles using the Naver API.
    """
    items = _search_naver_api(query, limit, sort, "blog")
    result = ""
    for i in items:
        result += f"title: {i['title']}\\n"
        result += f"description: {i['description']}\\n"
        result += "\\n"
    return result

@tool(show_result=True)
def search_naver_webkr(
    query: Annotated[str, "The query to search for"],
    limit: Annotated[int, "The number of web articles to return. (default: 15)"] = 15,
    sort: Annotated[Literal["sim", "date"], "The sort order of the web articles. 'sim' sorts by highest similarity first, 'date' sorts by most recent date first."] = "sim"
) -> str:
    """
    Search for web articles using the Naver API.
    """
    items = _search_naver_api(query, limit, sort, "webkr")
    result = ""
    for i in items:
        result += f"title: {i['title']}\\n"
        result += f"description: {i['description']}\\n"
        result += "\\n"
    return result