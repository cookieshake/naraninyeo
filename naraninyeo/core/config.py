import dotenv; dotenv.load_dotenv()
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # MongoDB settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "naraninyeo"

    # Naver API settings
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str

    # Gemini API settings
    GOOGLE_API_KEY: str

    # OpenAI API settings
    OPENAI_API_KEY: str

    # Kafka settings
    KAFKA_TOPIC: str = "naraninyeo-topic"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_GROUP_ID: str = "naraninyeo-group"

    # Naraninyeo API settings
    NARANINYEO_API_URL: str = "http://localhost:8000"

    # Ollama API settings
    OLLAMA_API_URL: str = "http://localhost:11434"

    # Qdrant settings
    QDRANT_URL: str = "http://localhost:6333"

settings = Settings()