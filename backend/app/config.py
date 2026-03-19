from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cozypup"
    strong_model: str = "deepseek/deepseek-chat"
    cheap_model: str = "qwen/qwen-turbo"
    google_places_api_key: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_access_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 30

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
