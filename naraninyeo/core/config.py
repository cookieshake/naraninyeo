from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Naraninyeo API"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"

settings = Settings() 