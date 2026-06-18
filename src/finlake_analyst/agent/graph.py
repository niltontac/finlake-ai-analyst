"""Grafo LangGraph — orquestra SQL generation, execução e interpretação financeira."""

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from finlake_analyst.agent.nodes import (
    handle_error,
    make_execute_sql_node,
    make_generate_sql_node,
    make_interpret_result_node,
)
from finlake_analyst.agent.state import AgentState
from finlake_analyst.config import get_settings
from finlake_analyst.prompts import get_interpretation_prompt
from finlake_analyst.tools.sql_execute import SqlExecuteTool

_MAX_RETRIES = 2


def _route_after_execute(state: AgentState) -> str:
    """Decide próximo nó após execute_sql com base no resultado e retry_count."""
    if state["sql_result"].startswith(("SQL_ERROR:", "SECURITY_ERROR:")):
        if state["retry_count"] >= _MAX_RETRIES:
            return "handle_error"
        return "generate_sql"
    return "interpret_result"


def create_agent_graph(sql_prompt: ChatPromptTemplate) -> CompiledStateGraph:
    """Cria e compila o grafo LangGraph do agente Text-to-SQL.

    Args:
        sql_prompt: Template com {schema} já pré-vinculado via .partial(schema=...).
                    A única variável livre restante é {question}.

    Returns:
        Grafo compilado pronto para .astream_events(initial_state, version="v2").
    """
    settings = get_settings()
    sql_llm = ChatAnthropic(
        model=settings.model_name,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )
    interpretation_llm = ChatAnthropic(
        model=settings.model_name,
        api_key=settings.anthropic_api_key,
    )
    tool = SqlExecuteTool()
    interpretation_prompt = get_interpretation_prompt()

    generate_sql = make_generate_sql_node(sql_llm, sql_prompt)
    execute_sql = make_execute_sql_node(tool)
    interpret_result = make_interpret_result_node(interpretation_llm, interpretation_prompt)

    graph: StateGraph = StateGraph(AgentState)

    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("interpret_result", interpret_result)
    graph.add_node("handle_error", handle_error)

    graph.add_edge(START, "generate_sql")
    graph.add_edge("generate_sql", "execute_sql")
    graph.add_conditional_edges(
        "execute_sql",
        _route_after_execute,
        {
            "generate_sql": "generate_sql",
            "interpret_result": "interpret_result",
            "handle_error": "handle_error",
        },
    )
    graph.add_edge("interpret_result", END)
    graph.add_edge("handle_error", END)

    return graph.compile()
