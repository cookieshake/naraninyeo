import httpx
from opentelemetry.trace import get_tracer

from naraninyeo.core.settings import Settings


class LlamaCppGemmaEmbedder:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.api_url = settings.LLAMA_CPP_EMBEDDINGS_URI
        self._client = client
        self._model: str | None = None

    async def _get_model(self) -> str:
        if self._model is None:
            resp = await self._client.get(f"{self.api_url}/v1/models")
            resp.raise_for_status()
            self._model = resp.json()["data"][0]["id"]
        return self._model

    @get_tracer(__name__).start_as_current_span("embed_docs")
    async def embed_docs(self, docs: list[str]) -> list[list[float]]:
        model = await self._get_model()
        transformed = [f"title: none | text: {content}" for content in docs]
        response = await self._client.post(
            f"{self.api_url}/v1/embeddings", json={"model": model, "input": transformed}, timeout=60.0
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    @get_tracer(__name__).start_as_current_span("embed_queries")
    async def embed_queries(self, queries: list[str]) -> list[list[float]]:
        model = await self._get_model()
        transformed = [f"task: search result | query: {content}" for content in queries]
        response = await self._client.post(
            f"{self.api_url}/v1/embeddings", json={"model": model, "input": transformed}, timeout=60.0
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]
