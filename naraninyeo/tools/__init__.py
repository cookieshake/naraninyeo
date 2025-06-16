from haystack.tools import Toolset
from naraninyeo.tools.history import get_history_by_timestamp
from naraninyeo.tools.search import search_naver_news, search_naver_blog, search_naver_webkr

default_toolset = Toolset(
    tools=[
        get_history_by_timestamp,
        search_naver_news,
        search_naver_blog,
        search_naver_webkr
    ]
)