from naraninyeo.core.models.reply import ReplyContext
from naraninyeo.core.models.retrieval import RetrievalResult
from naraninyeo.infrastructure.retrieval.rank import HeuristicRetrievalRanker
from naraninyeo.infrastructure.settings import Settings


class DefaultRetrievalPostProcessor:
    def __init__(self, settings: Settings, ranker: HeuristicRetrievalRanker):
        self.settings = settings
        self.ranker = ranker

    def process(self, results: list[RetrievalResult], context: ReplyContext) -> list[RetrievalResult]:
        # 1) drop empty contents
        filt = [r for r in results if r.content and r.content.strip()]
        # 2) dedupe by (ref, content)
        seen: set[tuple[str, str]] = set()
        deduped: list[RetrievalResult] = []
        for r in filt:
            try:
                as_text_attr = getattr(r.ref, "as_text", None)
                if callable(as_text_attr):
                    ref_val_str: str = str(as_text_attr())
                elif isinstance(as_text_attr, str):
                    ref_val_str = as_text_attr
                else:
                    ref_val_str = str(r.ref)
            except Exception:
                ref_val_str = str(r.ref)
            key = (ref_val_str, r.content.strip())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        # 3) rank by heuristic
        try:
            deduped.sort(key=lambda r: self.ranker.score(r), reverse=True)
        except Exception:
            # fallback to recency
            deduped.sort(key=lambda r: (r.source_timestamp is not None, r.source_timestamp or 0), reverse=True)
        # 4) cap by setting
        return deduped[: max(1, self.settings.MAX_KNOWLEDGE_REFERENCES)]
