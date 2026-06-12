"""Configuração centralizada do finlake-analyst via variáveis de ambiente."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação — carregada do .env na inicialização."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    model_name: str = Field(default="claude-sonnet-4-6", description="LLM model name")

    # PostgreSQL Gold (finlake-brasil :5433)
    finlake_database_url: str = Field(
        ...,
        description="PostgreSQL connection URL — aponta para finlake-brasil :5433",
    )

    # LangFuse Cloud
    langfuse_public_key: str = Field(..., description="LangFuse public key (pk-lf-...)")
    langfuse_secret_key: str = Field(..., description="LangFuse secret key (sk-lf-...)")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        description="LangFuse host",
    )

    # Chainlit
    chainlit_auth_secret: str = Field(..., description="Chainlit auth secret")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância singleton de Settings (cached)."""
    return Settings()
