import httpx
from opentelemetry import trace
from naraninyeo.core.config import settings

tracer = trace.get_tracer(__name__)

OLLAMA_API_URL = settings.OLLAMA_API_URL
EMBEDDING_MODEL = "hf.co/Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"

@tracer.start_as_current_span("get_embeddings")
async def get_embeddings(text: list[str]) -> list[list[float]]:
    """
    주어진 텍스트에 대한 임베딩을 Ollama API로부터 가져옵니다.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{OLLAMA_API_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": text},
            timeout=20
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embeddings", [])
