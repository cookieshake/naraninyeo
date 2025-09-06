from datetime import datetime, timezone, timedelta

from naraninyeo.domain.gateway.retrieval_rank import RetrievalRanker
from naraninyeo.domain.model.retrieval import RetrievalResult
from naraninyeo.infrastructure.settings import Settings


class HeuristicRetrievalRanker(RetrievalRanker):
    """Heuristic ranker using settings-driven weights and recency bonus."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def score(self, item: RetrievalResult) -> float:
        score = 1.0
        try:
            st = item.plan.search_type
        except Exception:
            st = None
        score += float(self.settings.RANK_WEIGHTS.get(st or "", 0.0))

        ts = item.source_timestamp
        if isinstance(ts, datetime):
            try:
                now = datetime.now(ts.tzinfo or timezone.utc)
                window = timedelta(hours=int(self.settings.RECENCY_WINDOW_HOURS))
                age = now - ts
                if age <= window:
                    frac = max(0.0, 1.0 - age.total_seconds() / window.total_seconds())
                    score += float(self.settings.RECENCY_BONUS_MAX) * frac
            except Exception:
                pass
        return score
