from abc import ABC, abstractmethod
from typing import override
from opentelemetry.trace import get_tracer

from naraninyeo.infrastructure.settings import Settings

import httpx


class TextEmbedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class Qwen306TextEmbedder(TextEmbedder):
    def __init__(self, settings: Settings):
        self.api_url = settings.LLAMA_CPP_EMBEDDINGS_URL
        self.model = "qwen3-embedding-0.6b"

    @override
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
            return [item.get("embedding", []) for item in data]
