

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    LLAMA_CPP_EMBEDDINGS_URI: str = "http://localhost:8080"
    VCHORD_URI: str = "postgresql://postgres:postgres@localhost:5432/naraninyeo"
