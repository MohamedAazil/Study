from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_storage_bucket: str = "documents"
    signed_url_expiry_seconds: int = 3600

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_index_name: str = "study-assistant"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    pinecone_materials_namespace: str = "materials"
    pinecone_pastpapers_namespace: str = "pastpapers"
    embedding_dimension: int = 3072

    # LLM providers (ordered; first = primary, rest = fallbacks)
    generation_providers: Annotated[list[str], NoDecode] = ["openai", "anthropic", "cohere"]
    embedding_providers: Annotated[list[str], NoDecode] = ["openai", "cohere"]
    llm_max_attempts: int = 3
    llm_retry_max_wait_seconds: float = 8.0
    llm_request_timeout_seconds: float = 60.0

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"

    anthropic_api_key: str = ""
    anthropic_chat_model: str = "claude-3-5-sonnet-latest"

    cohere_api_key: str = ""
    cohere_chat_model: str = "command-r-plus"
    cohere_embedding_model: str = "embed-english-v3.0"

    # RAG / ingestion
    chunk_size: int = 1200
    chunk_overlap: int = 200
    chat_top_k: int = 6
    examiner_top_k: int = 20

    # Notifications
    resend_api_key: str = ""
    email_from: str = "Study Assistant <reports@example.com>"
    frontend_url: str = "http://localhost:5173"

    # End-of-day job
    enable_scheduler: bool = False
    eod_cron_hour: int = 20
    eod_cron_minute: int = 0
    eod_timezone: str = "UTC"

    @field_validator("cors_origins", "generation_providers", "embedding_providers", mode="before")
    @classmethod
    def _parse_list(cls, value: object) -> object:
        return _split_csv(value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
