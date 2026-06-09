"""Testes de SqlExecuteTool com mock de SQLDatabase."""

from unittest.mock import MagicMock, patch

import pytest

from finlake_analyst.tools.sql_execute import SqlExecuteTool, _maybe_add_limit

_MOCK_RESULT = "date|taxa_anual\n2024-01-01|11.75\n2024-02-01|11.25"


@pytest.fixture()
def tool() -> SqlExecuteTool:
    return SqlExecuteTool()


@pytest.fixture()
def mock_db() -> MagicMock:
    with patch("finlake_analyst.tools.sql_execute.get_database") as mock:
        db = MagicMock()
        db.run.return_value = _MOCK_RESULT
        mock.return_value = db
        yield db


def test_select_returns_result(tool: SqlExecuteTool, mock_db: MagicMock) -> None:
    """SELECT válido retorna dados sem exceção."""
    result = tool._run("SELECT date, taxa_anual FROM macro_mensal LIMIT 3")
    assert "SQL_ERROR" not in result
    assert "SECURITY_ERROR" not in result
    assert len(result) > 0


def test_delete_rejected(tool: SqlExecuteTool) -> None:
    """DELETE é rejeitado com SECURITY_ERROR sem chamar o banco."""
    result = tool._run("DELETE FROM gold_cvm.fundo_mensal")
    assert result.startswith("SECURITY_ERROR")


def test_update_rejected(tool: SqlExecuteTool) -> None:
    """UPDATE é rejeitado com SECURITY_ERROR."""
    result = tool._run("UPDATE gold_bcb.macro_mensal SET taxa_anual=0")
    assert result.startswith("SECURITY_ERROR")


def test_sql_error_returned_as_string(tool: SqlExecuteTool, mock_db: MagicMock) -> None:
    """Erro PostgreSQL retornado como string prefixada, não como exceção."""
    mock_db.run.side_effect = Exception("column x does not exist")
    result = tool._run("SELECT coluna_inexistente FROM macro_mensal")
    assert result.startswith("SQL_ERROR")
    assert "column x does not exist" in result


def test_limit_added_when_absent(tool: SqlExecuteTool, mock_db: MagicMock) -> None:
    """LIMIT 50 adicionado automaticamente quando ausente."""
    tool._run("SELECT date FROM macro_mensal")
    called_query: str = mock_db.run.call_args[0][0]
    assert "LIMIT" in called_query.upper()


def test_cte_select_accepted(tool: SqlExecuteTool, mock_db: MagicMock) -> None:
    """CTE com SELECT final é aceito."""
    cte = "WITH base AS (SELECT date FROM macro_mensal) SELECT * FROM base"
    result = tool._run(cte)
    assert not result.startswith("SECURITY_ERROR")


def test_maybe_add_limit_adds_when_absent() -> None:
    """_maybe_add_limit adiciona LIMIT 50 quando ausente."""
    assert "LIMIT 50" in _maybe_add_limit("SELECT 1")


def test_maybe_add_limit_preserves_existing() -> None:
    """_maybe_add_limit não duplica LIMIT existente."""
    query = "SELECT 1 LIMIT 10"
    assert _maybe_add_limit(query) == query
