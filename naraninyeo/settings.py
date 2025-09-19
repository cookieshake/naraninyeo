"""Application configuration powered by pydantic settings."""

from __future__ import annotations

import dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

dotenv.load_dotenv()


class Settings(BaseSettings):
    """Runtime configuration with sensible defaults for local development."""

    # MongoDB settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "naraninyeo"

    # Naver API settings
    NAVER_CLIENT_ID: str = ""
    NAVER_CLIENT_SECRET: str = ""

    # Kafka settings
    KAFKA_TOPIC: str = "naraninyeo-topic"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_GROUP_ID: str = "naraninyeo-group"

    # Naraninyeo API settings
    NARANINYEO_API_URL: str = "http://localhost:8000"
    NARANINYEO_NEW_MESSAGE_API: str = "http://localhost:8001"

    # LLM API settings
    LLAMA_CPP_EMBEDDINGS_URL: str = "http://localhost:11435/model"

    # Qdrant settings
    QDRANT_URL: str = "http://localhost:6333"

    # LLM settings
    HISTORY_LIMIT: int = 10
    DEFAULT_SEARCH_LIMIT: int = 3
    TIMEZONE: str = "Asia/Seoul"
    LOCATION: str = "Seoul, South Korea"

    # Bot info
    BOT_AUTHOR_ID: str = "bot-naraninyeo"
    BOT_AUTHOR_NAME: str = "나란잉여"

    # OpenRouter API settings
    OPENROUTER_API_KEY: str = ""

    # LLM provider selection (via registry)
    # Available out of the box: "openrouter"
    LLM_PROVIDER: str = "openrouter"

    # Health check server settings
    PORT: int = 8080

    REPLY_TEXT_PREFIX: str = ""

    # Memory settings
    MEMORY_TTL_HOURS: int = 6

    # Retrieval post-processing
    MAX_KNOWLEDGE_REFERENCES: int = 8

    # LLM model names and timeouts
    REPLY_MODEL_NAME: str = "anthropic/claude-sonnet-4"
    PLANNER_MODEL_NAME: str = "openai/gpt-4.1-mini"
    MEMORY_MODEL_NAME: str = "openai/gpt-5-nano"
    EXTRACTOR_MODEL_NAME: str = "openai/gpt-4.1-nano"
    LLM_TIMEOUT_SECONDS_REPLY: int = 20
    LLM_TIMEOUT_SECONDS_PLANNER: int = 20
    LLM_TIMEOUT_SECONDS_MEMORY: int = 8
    LLM_TIMEOUT_SECONDS_EXTRACTOR: int = 5

    # Retrieval executor behavior
    RETRIEVAL_MAX_CONCURRENCY: int = 8

    # Retrieval strategy toggles
    ENABLED_RETRIEVAL_STRATEGIES: list[str] = ["naver_search", "wikipedia", "chat_history"]

    # Ranking weights per search_type
    RANK_WEIGHTS: dict[str, float] = {
        "naver_news": 0.6,
        "naver_doc": 0.3,
        "naver_blog": 0.2,
        "naver_web": 0.1,
        "chat_history": 0.1,
        "wikipedia": 0.25,
    }
    RECENCY_WINDOW_HOURS: int = 24
    RECENCY_BONUS_MAX: float = 0.5

    # Plugin modules to auto-load at startup (e.g., ["my_pkg.plugins.search_bing"])
    PLUGINS: list[str] = []

    # Pipeline order (override to customize flow). If empty, uses built-in default.
    PIPELINE: list[str] = []

    @field_validator("ENABLED_RETRIEVAL_STRATEGIES")
    @classmethod
    def _validate_strategies(cls, value: list[str]) -> list[str]:
        allowed = {"naver_search", "wikipedia", "chat_history"}
        invalid = [item for item in value if item not in allowed]
        if invalid:
            raise ValueError(
                f"Unknown strategies in ENABLED_RETRIEVAL_STRATEGIES: {invalid}"
            )
        return value

    @field_validator("RANK_WEIGHTS")
    @classmethod
    def _validate_weights(cls, value: dict[str, float]) -> dict[str, float]:
        for key, val in value.items():
            if not isinstance(val, (int, float)) or not (-1.0 <= float(val) <= 5.0):
                raise ValueError(f"RANK_WEIGHTS[{key}] must be between -1.0 and 5.0")
        return value
