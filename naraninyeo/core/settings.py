from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG_MODE: bool = False
    LLAMA_CPP_EMBEDDINGS_URI: str = "http://localhost:8080"
    VCHORD_URI: str = "postgresql://postgres:postgres@localhost:5432/naraninyeo"
    NAVER_CLIENT_ID: str = "your_naver_client_id"
    NAVER_CLIENT_SECRET: str = "your_naver_client_secret"
