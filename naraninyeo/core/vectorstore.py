from qdrant_client import AsyncQdrantClient
from naraninyeo.core.config import settings


vc = AsyncQdrantClient(url=settings.QDRANT_URL)

