import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = "familyhealth"
    pg_password: str = "changeme"
    pg_database: str = "familyhealth"
    pg_mem0_database: str = "mem0_db"

    # Supabase
    supabase_url: str = ""
    supabase_service_key: str = ""

    # LLM — Gemini (primary provider in prod)
    gemini_api_key: str = ""
    gemini_diagnosis_model: str = "gemini-2.5-flash"
    gemini_report_model: str = "gemini-2.5-flash"
    gemini_flash_model: str = "gemini-2.5-flash-lite"
    gemini_flash_lite_new_model: str = "gemini-3.1-flash-lite-preview"

    # LLM — Qwen via Ollama Cloud (dev/fallback)
    qwen_api_key: str = ""
    qwen_base_url: str = "https://ollama.com/v1"
    qwen_model: str = "qwen3.5:397b"

    # LLM — Cerebras (dev/fallback)
    cerebras_api_key: str = ""
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_model: str = "gpt-oss-120b"

    # LLM routing — set provider name per task (e.g., "cerebras", "gemini", "qwen").
    # Empty = use default (gemini for all tasks).
    # Dev environments should override these to use free providers.
    llm_route_chat: str = ""
    llm_route_diagnosis: str = ""
    llm_route_report_analysis: str = ""
    llm_route_topic_generation: str = ""
    llm_route_summarization: str = ""
    llm_route_fact_extraction: str = ""

    # Web search
    tavily_api_key: str = ""
    serper_api_keys: str = ""  # comma-separated keys for round-robin rotation
    langsearch_api_keys: str = ""  # comma-separated keys for round-robin rotation

    # Embeddings (Gemini for Mem0 vector store — reuses gemini_api_key)
    embedding_model: str = "models/gemini-embedding-001"
    embedding_dims: int = 768

    # Reports
    max_report_file_size: int = 20_971_520  # 20 MB

    # Data retention
    llm_trace_retention_days: int = 30

    # Sentry (optional — error monitoring)
    sentry_dsn: str = ""

    # App
    app_env: str = "development"
    log_level: str = "info"
    log_dir: str = "logs"
    allowed_origins: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        )

    def validate_prod_secrets(self) -> None:
        """Fail fast if required secrets are missing in production."""
        if self.app_env != "production":
            return
        missing = []
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_service_key:
            missing.append("SUPABASE_SERVICE_KEY")
        if self.pg_password == "changeme":
            missing.append("PG_PASSWORD (still default 'changeme')")
        if not self.allowed_origins:
            missing.append("ALLOWED_ORIGINS")
        if missing:
            raise RuntimeError(
                f"Production startup blocked — missing required config: {missing}"
            )


settings = Settings()
