import dotenv
from pydantic_settings import BaseSettings

dotenv.load_dotenv()


class Settings(BaseSettings):
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

    # LLM API settings
    LLAMA_CPP_EMBEDDINGS_URL: str = "http://localhost:11435/model"

    # Qdrant settings
    QDRANT_URL: str = "http://localhost:6333"

    # LLM settings
    HISTORY_LIMIT: int = 10
    DEFAULT_SEARCH_LIMIT: int = 3
    TIMEZONE: str = "Asia/Seoul"
    LOCATION: str = "Seoul, South Korea"

    # 봇 정보
    BOT_AUTHOR_ID: str = "bot-naraninyeo"
    BOT_AUTHOR_NAME: str = "나란잉여"

    # OpenRouter API settings
    OPENROUTER_API_KEY: str = ""

    # Health check server settings
    PORT: int = 8080
