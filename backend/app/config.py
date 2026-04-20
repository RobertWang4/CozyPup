from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cozypup"
    # Main model — used for chat orchestration, tool execution, profile extraction, and context summary.
    # Change this ONE value to test a different model for all normal operations.
    model: str = "openai/grok-4-1-fast-non-reasoning"
    # Emergency model — only used when emergency keywords are detected (e.g. seizure, poisoning).
    # Typically a more capable/accurate model for safety-critical responses.
    emergency_model: str = "openai/kimi-k2.5"
    embedding_model: str = "openai/text-embedding-3-small"
    # RAG retrieval — drop results whose cosine distance exceeds this threshold.
    # Empirically: <0.3 very relevant, 0.3–0.5 loosely related, >0.6 mostly noise.
    rag_distance_threshold: float = 0.6
    # In-process LRU cache for query embeddings. Set to 0 to disable.
    rag_embed_cache_size: int = 256
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
    apple_bundle_id: str = "com.cozypup.app"  # Also used for Apple Sign-In audience verification
    google_client_id: str = "496617144117-73j9krtarupr8as09cka2tg06sn4cke8.apps.googleusercontent.com"

    # Google OAuth — Web application client (used for the /invite landing page only).
    # Separate from google_client_id, which is the iOS native client used by
    # iOS Sign in with Google. Populated from Secret Manager in production.
    google_web_client_id: str = ""
    google_web_client_secret: str = ""

    # Sign in with Apple (web) — for the /invite landing page.
    # Different from iOS Sign in with Apple: the web flow uses a separate
    # Services ID (not the app Bundle ID), and the client_secret is a
    # short-lived JWT we sign ourselves with a private key (.p8).
    #
    # apple_web_service_id: the Services ID registered in Apple Developer
    #   (e.g. "com.cozypup.app.web")
    # apple_web_key_id: 10-char Key ID from Apple Developer → Keys
    # apple_web_private_key: PEM contents of the .p8 file (starts with
    #   "-----BEGIN PRIVATE KEY-----"). Stored in Secret Manager, injected
    #   as an env var. Newlines in env vars are preserved verbatim.
    # apple_web_team_id: Apple Developer Team ID. Falls back to apns_team_id
    #   if not explicitly set — they are the same Team.
    # apple_web_domain_association: contents of the Apple domain association
    #   file served at /.well-known/apple-developer-domain-association.
    #   Apple downloads this to verify we own the domain.
    apple_web_service_id: str = ""
    apple_web_key_id: str = ""
    apple_web_private_key: str = ""
    apple_web_team_id: str = ""
    apple_web_domain_association: str = ""
    apns_bundle_id: str = "com.cozypup.app"
    apns_use_sandbox: bool = True  # True for dev, False for production

    # Apple In-App Purchase / StoreKit 2
    # app_apple_id is the numeric Apple ID from App Store Connect (Apple ID under your app listing)
    app_apple_id: int = 6761727110
    # True for sandbox/TestFlight, False for App Store production. Clients may override via X-Apple-Env header.
    iap_sandbox: bool = True

    # Server public URL (for constructing image URLs for LLM vision)
    server_public_url: str = "http://168.138.75.153:8000"

    gcs_bucket: str = ""  # GCS bucket for file uploads (e.g. "cozypup-avatars")

    # Deployment environment — "dev" enables unsafe endpoints (e.g. /admin/auth/dev-login).
    # Set via ENVIRONMENT env var in Cloud Run. Defaults to "dev" locally.
    environment: str = "dev"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
