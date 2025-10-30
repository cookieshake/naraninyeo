

from typing import Any
import httpx

from naraninyeo.core.settings import Settings


class LlamaCppGemmaEmbedder:
    def __init__(self, settings: Settings) -> None:
        self.api_url = settings.LLAMA_CPP_EMBEDDINGS_URI
        self.model = httpx.get(
            f"{self.api_url}/v1/models"
        ).json()["data"][0]["id"]

    async def embed_docs(self, docs: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            transformed = [
                f"title: none | text: {content}"
                for content in docs
            ]
            response = await client.post(
                f"{self.api_url}/v1/embeddings",
                json={
                    "model": self.model,
                    "input": transformed
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings

    async def embed_queries(self, queries: list[str]) -> list[list[float]]:
        transformed = [
            f"task: search result | query: {content}"
            for content in queries
        ]
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/v1/embeddings",
                json={
                    "model": self.model,
                    "input": transformed
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings