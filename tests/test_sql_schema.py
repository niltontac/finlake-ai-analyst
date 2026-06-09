"""Testes de SqlSchemaTool com mock de SQLDatabase."""

from unittest.mock import MagicMock, patch

import pytest

from finlake_analyst.tools.sql_schema import SqlSchemaTool

_SCHEMA_FIXTURE = (
    "CREATE TABLE macro_mensal (date DATE, taxa_anual NUMERIC(8,4), selic_real NUMERIC(8,4));\n"
    "CREATE TABLE fundo_mensal (cnpj_fundo VARCHAR(18), alpha_selic NUMERIC, gestor TEXT);\n"
    "3 rows from macro_mensal table:\ndate\ttaxa_anual\n2024-01-01\t11.75\n"
)


@pytest.fixture()
def tool() -> SqlSchemaTool:
    return SqlSchemaTool()


@pytest.fixture()
def mock_db() -> MagicMock:
    with patch("finlake_analyst.tools.sql_schema.get_database") as mock:
        db = MagicMock()
        db.get_table_info.return_value = _SCHEMA_FIXTURE
        mock.return_value = db
        yield db


def test_schema_returns_table_info(tool: SqlSchemaTool, mock_db: MagicMock) -> None:
    """get_schema retorna schema das tabelas."""
    result = tool._run("")
    assert "macro_mensal" in result
    assert "fundo_mensal" in result


def test_schema_includes_quality_notes(tool: SqlSchemaTool, mock_db: MagicMock) -> None:
    """Output inclui notas de qualidade dos dados."""
    result = tool._run("")
    assert any(keyword in result for keyword in ["gestor", "alpha_selic", "outlier"])


def test_schema_passes_table_names(tool: SqlSchemaTool, mock_db: MagicMock) -> None:
    """Nomes de tabelas são passados corretamente para get_table_info."""
    tool._run("fundo_mensal,macro_mensal")
    mock_db.get_table_info.assert_called_once_with(
        table_names=["fundo_mensal", "macro_mensal"]
    )
