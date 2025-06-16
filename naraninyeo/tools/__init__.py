from haystack.tools import Toolset
from naraninyeo.tools.history import get_history_by_timestamp

default_toolset = Toolset(
    tools=[
        get_history_by_timestamp,
    ]
)