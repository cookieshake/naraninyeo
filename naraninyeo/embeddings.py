"""Text embedding helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx
from opentelemetry.trace import get_tracer

from naraninyeo.settings import Settings


class TextEmbedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class Qwen306TextEmbedder(TextEmbedder):
    def __init__(self, settings: Settings):
        self.api_url = settings.LLAMA_CPP_EMBEDDINGS_URL
        self.model = "qwen3-embedding-0.6b"

    @get_tracer(__name__).start_as_current_span("embed texts")
    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/v1/embeddings",
                json={"model": self.model, "input": texts},
                timeout=60,
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            # llama.cpp 서버에서 돌려준 벡터 배열만 추려서 반환한다.
            return [item.get("embedding", []) for item in data]
