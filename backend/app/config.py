from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cozypup"
    default_model: str = "openai/qwen3.5-plus-2026-02-15"
    emergency_model: str = "openai/kimi-k2.5"
    model_api_base: str = ""   # Proxy base URL (e.g. https://api.shubiaobiao.cn/v1)
    model_api_key: str = ""    # Proxy API key
    context_model: str = "deepseek/deepseek-chat"  # cheap model for summarization
    google_places_api_key: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_access_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 30

    # APNs push notifications
    apns_key_path: str = ""        # Path to .p8 key file
    apns_key_id: str = ""          # 10-char Key ID from Apple Developer
    apns_team_id: str = ""         # Apple Developer Team ID
    apns_bundle_id: str = "com.cozypup.app"
    apns_use_sandbox: bool = True  # True for dev, False for production

    # Server public URL (for constructing image URLs for LLM vision)
    server_public_url: str = "http://168.138.75.153:8000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
