from pydantic_settings import BaseSettings, SettingsConfigDict


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
    supabase_jwt_secret: str = ""
    supabase_service_key: str = ""

    # LLM — Gemini
    gemini_api_key: str = ""
    gemini_diagnosis_model: str = "gemini-2.5-pro"
    gemini_flash_model: str = "gemini-2.0-flash"

    # LLM — Qwen via OpenRouter
    qwen_api_key: str = ""
    qwen_base_url: str = "https://openrouter.ai/api/v1"
    qwen_model: str = "qwen/qwen-2.5-72b-instruct"

    # Embeddings (Gemini for Mem0 vector store — reuses gemini_api_key)
    embedding_model: str = "models/text-embedding-004"
    embedding_dims: int = 768

    # App
    app_env: str = "development"
    log_level: str = "info"
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


settings = Settings()
