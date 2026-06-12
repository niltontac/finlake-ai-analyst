"""Testes do grafo LangGraph — compilação e lógica de routing."""

from unittest.mock import MagicMock, patch

from finlake_analyst.agent.graph import _route_after_execute, create_agent_graph
from finlake_analyst.agent.state import AgentState


def _state(**overrides: object) -> AgentState:
    """Cria estado base para testes de routing."""
    base: AgentState = {
        "question": "Qual a SELIC?",
        "sql": "SELECT 1",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ── routing ───────────────────────────────────────────────────────────────────


def test_route_success_goes_to_interpret_result() -> None:
    """Resultado sem prefixo de erro vai para interpret_result."""
    state = _state(sql_result="date|taxa\n2024-01-01|10.5", retry_count=0)
    assert _route_after_execute(state) == "interpret_result"


def test_route_sql_error_with_retry_available_goes_to_generate_sql() -> None:
    """SQL_ERROR + retry_count=0 (< 2) vai para generate_sql."""
    state = _state(sql_result="SQL_ERROR: column x does not exist", retry_count=0)
    assert _route_after_execute(state) == "generate_sql"


def test_route_sql_error_retry_count_1_still_retries() -> None:
    """SQL_ERROR + retry_count=1 (< 2) ainda vai para generate_sql."""
    state = _state(sql_result="SQL_ERROR: syntax error", retry_count=1)
    assert _route_after_execute(state) == "generate_sql"


def test_route_sql_error_retry_count_2_goes_to_handle_error() -> None:
    """SQL_ERROR + retry_count=2 (>= 2) vai para handle_error — AT-006."""
    state = _state(sql_result="SQL_ERROR: table not found", retry_count=2)
    assert _route_after_execute(state) == "handle_error"


def test_route_security_error_also_triggers_retry() -> None:
    """SECURITY_ERROR com retry disponível vai para generate_sql."""
    state = _state(sql_result="SECURITY_ERROR: Only SELECT allowed.", retry_count=0)
    assert _route_after_execute(state) == "generate_sql"


def test_route_empty_result_goes_to_interpret_result() -> None:
    """Resultado vazio (sem prefixo de erro) vai para interpret_result."""
    state = _state(sql_result="Query executada com sucesso. Nenhum resultado retornado.")
    assert _route_after_execute(state) == "interpret_result"


# ── graph compilation ─────────────────────────────────────────────────────────


@patch("finlake_analyst.agent.graph.ChatAnthropic")
@patch("finlake_analyst.agent.graph.get_settings")
def test_create_agent_graph_compiles(
    mock_get_settings: MagicMock,
    mock_chat_anthropic: MagicMock,
) -> None:
    """create_agent_graph() retorna grafo compilado sem lançar exceção — AT-001."""
    mock_get_settings.return_value.model_name = "claude-sonnet-4-6"
    mock_get_settings.return_value.anthropic_api_key = "sk-ant-fake"

    mock_prompt = MagicMock()
    graph = create_agent_graph(mock_prompt)

    assert graph is not None
    assert hasattr(graph, "astream_events")
    assert hasattr(graph, "ainvoke")
    mock_chat_anthropic.assert_called_once()
