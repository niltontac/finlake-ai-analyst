"""Testes de carregamento e validação de configuração."""

import pytest
from pydantic import ValidationError

from finlake_analyst.config import Settings, get_settings

_VALID_ENV: dict[str, str] = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "DATABASE_URL": "postgresql://user:pass@localhost:5433/finlake",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
    "LANGFUSE_SECRET_KEY": "sk-lf-test",
    "CHAINLIT_AUTH_SECRET": "test-secret",
}


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """Limpa cache de Settings entre testes."""
    get_settings.cache_clear()


def test_settings_loads_with_valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings carrega corretamente com todas as variáveis definidas."""
    for key, value in _VALID_ENV.items():
        monkeypatch.setenv(key, value)

    settings = Settings()

    assert settings.model_name == "claude-sonnet-4-6"
    assert settings.langfuse_host == "https://cloud.langfuse.com"
    assert settings.anthropic_api_key == "sk-ant-test"


def test_settings_missing_required_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """ValidationError com campo identificado quando variável obrigatória ausente."""
    for key, value in _VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # ignora .env real para isolar o teste

    assert "anthropic_api_key" in str(exc_info.value).lower()


def test_model_name_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    """MODEL_NAME pode ser sobrescrito via variável de ambiente."""
    for key, value in _VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MODEL_NAME", "claude-opus-4-8")

    settings = Settings()

    assert settings.model_name == "claude-opus-4-8"
