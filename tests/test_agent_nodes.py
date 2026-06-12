"""Testes unitários dos nós do agente — sem banco ou API real."""

from unittest.mock import AsyncMock, MagicMock

from finlake_analyst.agent.nodes import (
    handle_error,
    make_execute_sql_node,
    make_generate_sql_node,
    make_interpret_result_node,
)
from finlake_analyst.agent.state import AgentState


def _state(**overrides: object) -> AgentState:
    """Cria estado base com valores padrão para testes."""
    base: AgentState = {
        "question": "Qual a SELIC atual?",
        "sql": "",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ── generate_sql ──────────────────────────────────────────────────────────────


async def test_generate_sql_returns_sql_in_state() -> None:
    """Nó retorna SQL no campo 'sql' do state."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="SELECT 1"))
    mock_prompt = MagicMock()
    mock_prompt.format_messages = MagicMock(return_value=[])

    node = make_generate_sql_node(mock_llm, mock_prompt)
    result = await node(_state())

    assert result["sql"] == "SELECT 1"


async def test_generate_sql_strips_whitespace() -> None:
    """SQL com espaços/newlines extras é limpo via .strip()."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="  SELECT 1\n"))
    mock_prompt = MagicMock()
    mock_prompt.format_messages = MagicMock(return_value=[])

    node = make_generate_sql_node(mock_llm, mock_prompt)
    result = await node(_state())

    assert result["sql"] == "SELECT 1"


async def test_generate_sql_retry_includes_error_context() -> None:
    """Em retry, o contexto de erro é incluído na pergunta ao LLM."""
    captured: list[dict] = []
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="SELECT 2"))
    mock_prompt = MagicMock()
    mock_prompt.format_messages = MagicMock(
        side_effect=lambda **kw: captured.append(kw) or []
    )

    state = _state(retry_count=1, sql="SELECT bad", error="SQL_ERROR: column x does not exist")
    node = make_generate_sql_node(mock_llm, mock_prompt)
    await node(state)

    assert len(captured) == 1
    question_sent = captured[0]["question"]
    assert "column x does not exist" in question_sent


async def test_generate_sql_no_error_context_on_first_attempt() -> None:
    """Na primeira tentativa (retry_count=0), a pergunta não contém contexto de erro."""
    captured: list[dict] = []
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="SELECT 1"))
    mock_prompt = MagicMock()
    mock_prompt.format_messages = MagicMock(
        side_effect=lambda **kw: captured.append(kw) or []
    )

    node = make_generate_sql_node(mock_llm, mock_prompt)
    await node(_state(retry_count=0))

    assert "[Tentativa anterior falhou]" not in captured[0]["question"]


# ── execute_sql ───────────────────────────────────────────────────────────────


async def test_execute_sql_success_clears_error_and_stores_result() -> None:
    """Sucesso limpa error e armazena sql_result."""
    mock_tool = MagicMock()
    mock_tool._arun = AsyncMock(return_value="date|taxa\n2024-01-01|10.5")

    node = make_execute_sql_node(mock_tool)
    result = await node(_state(sql="SELECT date, taxa FROM macro_mensal LIMIT 5"))

    assert result["sql_result"] == "date|taxa\n2024-01-01|10.5"
    assert result["error"] is None


async def test_execute_sql_error_increments_retry_count() -> None:
    """SQL_ERROR incrementa retry_count de 0 para 1."""
    mock_tool = MagicMock()
    mock_tool._arun = AsyncMock(return_value="SQL_ERROR: column x does not exist")

    node = make_execute_sql_node(mock_tool)
    result = await node(_state(sql="SELECT bad", retry_count=0))

    assert result["retry_count"] == 1
    assert result["sql_result"].startswith("SQL_ERROR:")
    assert result["error"].startswith("SQL_ERROR:")


async def test_execute_sql_security_error_also_increments_retry() -> None:
    """SECURITY_ERROR também incrementa retry_count."""
    mock_tool = MagicMock()
    mock_tool._arun = AsyncMock(return_value="SECURITY_ERROR: Only SELECT queries are allowed.")

    node = make_execute_sql_node(mock_tool)
    result = await node(_state(sql="DELETE FROM table", retry_count=0))

    assert result["retry_count"] == 1


async def test_execute_sql_calls_tool_with_state_sql() -> None:
    """Tool é chamada com o SQL do state."""
    mock_tool = MagicMock()
    mock_tool._arun = AsyncMock(return_value="resultado")

    node = make_execute_sql_node(mock_tool)
    await node(_state(sql="SELECT taxa FROM macro_mensal LIMIT 5"))

    mock_tool._arun.assert_called_once_with("SELECT taxa FROM macro_mensal LIMIT 5")


# ── interpret_result ──────────────────────────────────────────────────────────


async def test_interpret_result_returns_analysis() -> None:
    """Nó retorna análise financeira no campo 'analysis' do state."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(content="A SELIC está em 10.75% ao ano.")
    )
    mock_prompt = MagicMock()
    mock_prompt.format_messages = MagicMock(return_value=[])

    node = make_interpret_result_node(mock_llm, mock_prompt)
    result = await node(_state(sql="SELECT 1", sql_result="10.75"))

    assert result["analysis"] == "A SELIC está em 10.75% ao ano."


async def test_interpret_result_passes_question_sql_result_to_prompt() -> None:
    """Prompt recebe question, sql e result do state."""
    captured: list[dict] = []
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="análise"))
    mock_prompt = MagicMock()
    mock_prompt.format_messages = MagicMock(
        side_effect=lambda **kw: captured.append(kw) or []
    )

    state = _state(
        question="Qual a SELIC?",
        sql="SELECT taxa FROM macro_mensal",
        sql_result="10.75",
    )
    node = make_interpret_result_node(mock_llm, mock_prompt)
    await node(state)

    assert captured[0]["question"] == "Qual a SELIC?"
    assert captured[0]["sql"] == "SELECT taxa FROM macro_mensal"
    assert captured[0]["result"] == "10.75"


# ── handle_error ──────────────────────────────────────────────────────────────


def test_handle_error_does_not_expose_sql_error() -> None:
    """Mensagem de erro não contém 'SQL_ERROR' nem detalhes técnicos."""
    state = _state(error="SQL_ERROR: column x does not exist", retry_count=2)
    result = handle_error(state)

    assert "SQL_ERROR" not in result["analysis"]
    assert "column x" not in result["analysis"]


def test_handle_error_returns_portuguese_text() -> None:
    """Mensagem de erro está em português."""
    state = _state(error="SQL_ERROR: syntax error", retry_count=2)
    result = handle_error(state)

    portuguese_keywords = ["não", "dados", "pergunta", "consulta", "disponível"]
    assert any(kw in result["analysis"].lower() for kw in portuguese_keywords)


def test_handle_error_analysis_is_nonempty() -> None:
    """Campo analysis é preenchido com texto não-vazio."""
    result = handle_error(_state(retry_count=2))
    assert len(result["analysis"]) > 10
