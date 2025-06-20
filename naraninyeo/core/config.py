from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Naraninyeo API"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # MongoDB settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "naraninyeo"

    # Naver API settings
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str

    # Gemini API settings
    GOOGLE_API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings() 