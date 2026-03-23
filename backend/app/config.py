from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cozypup"
    default_model: str = "openai/qwen3.5-plus-2026-02-15"
    emergency_model: str = "openai/kimi-k2.5"
    model_api_base: str = ""   # Proxy base URL (e.g. https://api.shubiaobiao.cn/v1)
    model_api_key: str = ""    # Proxy API key
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

    firebase_project_id: str = "cozypup-39487"

    # Server public URL (for constructing image URLs for LLM vision)
    server_public_url: str = "http://168.138.75.153:8000"

    # RAG settings
    embedding_model: str = "text-embedding-3-small"
    embedding_api_base: str = ""       # Separate proxy URL for embeddings
    embedding_api_key: str = ""        # Separate API key for embeddings
    embedding_dimensions: int = 1536
    rag_chat_token_budget: int = 1500
    rag_calendar_token_budget: int = 1500
    rag_retrieval_timeout: float = 2.0
    rag_score_threshold: float = 0.3   # Min cosine similarity to include

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
