from naraninyeo.domain.gateway.retrieval_post import RetrievalPostProcessor
from naraninyeo.domain.gateway.retrieval_rank import RetrievalRanker
from naraninyeo.domain.model.reply import ReplyContext
from naraninyeo.domain.model.retrieval import RetrievalResult
from naraninyeo.infrastructure.settings import Settings


class DefaultRetrievalPostProcessor(RetrievalPostProcessor):
    def __init__(self, settings: Settings, ranker: RetrievalRanker):
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
                ref_val = r.ref.as_text if hasattr(r.ref, "as_text") else str(r.ref)
            except Exception:
                ref_val = str(r.ref)
            key = (ref_val, r.content.strip())
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
