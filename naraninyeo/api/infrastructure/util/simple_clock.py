import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


class SimpleClock:
    def now(self) -> datetime:
        if os.environ.get("TZ"):
            tz = ZoneInfo(os.environ["TZ"])
        else:
            tz = ZoneInfo("Asia/Seoul")
        return datetime.now(tz=tz)
