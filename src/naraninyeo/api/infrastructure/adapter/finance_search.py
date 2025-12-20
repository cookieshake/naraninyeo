from datetime import datetime, timedelta
from functools import reduce

import FinanceDataReader as fdr
import httpx
from cachetools import TTLCache, cached
from pydantic import BaseModel


class Ticker(BaseModel):
    code: str
    reuter_code: str
    type: str
    name: str
    nation: str
    url: str
    category: str


class NewsSearchResult(BaseModel):
    source: str
    timestamp: str
    title: str
    body: str


class PriceInfo(BaseModel):
    local_date: str
    close_price: float


class FinanceSearchClient:
    @cached(cache=TTLCache(maxsize=100, ttl=86400))
    async def search_symbol(self, query: str) -> Ticker | None:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://m.stock.naver.com/front-api/search/autoComplete",
                params={
                    "query": query,
                    "target": "stock,index,marketindicator,coin,ipo",
                },
            )
        if response.status_code != 200:
            raise Exception(f"Failed to search symbol: {response.status_code}, {response.text}")
        response = response.json()
        result = []
        for item in response["result"]["items"]:
            result.append(
                Ticker(
                    code=item["code"],
                    reuter_code=item["reutersCode"],
                    type=item["typeCode"],
                    name=item["name"],
                    nation=item["nationCode"],
                    url=item["url"],
                    category=item["category"],
                )
            )
        if not result:
            return None
        return result[0]

    async def search_news(self, symbol: Ticker) -> list[NewsSearchResult]:
        """주어진 쿼리에 해당하는 종목에 대한 뉴스를 검색합니다."""
        if symbol.nation == "KOR":
            url = f"https://m.stock.naver.com/api/news/stock/{symbol.reuter_code}"
        else:
            url = f"https://api.stock.naver.com/news/worldStock/{symbol.reuter_code}"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={
                    "pageSize": 20,
                    "page": 1,
                },
            )
        if response.status_code != 200:
            raise Exception(f"Failed to search news: {response.status_code}, {response.text}")
        response = response.json()
        result = []
        if symbol.nation == "KOR":
            items = [r["items"] for r in response]
            items = reduce(lambda x, y: x + y, items)
        else:
            items = response
        for item in items:
            result.append(
                NewsSearchResult(
                    source=item.get("officeName", "") or item.get("ohnm", ""),
                    timestamp=item.get("datetime", "") or item.get("dt", ""),
                    title=item.get("title", "") or item.get("tit", ""),
                    body=item.get("body", "") or item.get("subcontent", ""),
                )
            )
        if not result:
            return []
        return result

    async def search_current_price(self, symbol: Ticker) -> str | None:
        if "domestic" in symbol.url.lower():
            url = f"https://polling.finance.naver.com/api/realtime/domestic/{symbol.category}/{symbol.reuter_code}"
        else:
            url = f"https://polling.finance.naver.com/api/realtime/worldstock/{symbol.category}/{symbol.reuter_code}"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
            )
            if response.status_code != 200:
                raise Exception(f"Failed to search current price: {response.status_code}, {response.text}")
            response = response.json()
        if len(response["datas"]) == 0:
            return None
        return response["datas"][0]["closePrice"]

    async def get_short_term_price(self, symbol: Ticker) -> list[PriceInfo]:
        """주어진 쿼리에 해당하는 종목에 대한 단기간의 종가를 검색합니다"""
        df = fdr.DataReader(symbol.code.strip("."), start=datetime.now() - timedelta(days=30))
        result = []
        for item in df.iloc[-15:-1].iterrows():
            result.append(
                PriceInfo(
                    local_date=item[0].strftime("%Y-%m-%d"),
                    close_price=item[1].Close,
                )
            )
        if not result:
            return []
        return result

    async def get_long_term_price(self, symbol: Ticker) -> list[PriceInfo]:
        """주어진 쿼리에 해당하는 종목에 대한 장기간의 종가를 검색합니다"""
        df = fdr.DataReader(symbol.code.strip("."), start="1990-01-01")
        result = []
        for item in df.iloc[:: int(len(df) / 100)].iterrows():
            result.append(
                PriceInfo(
                    local_date=item[0].strftime("%Y-%m-%d"),
                    close_price=item[1].Close,
                )
            )
        if not result:
            return []
        return result
