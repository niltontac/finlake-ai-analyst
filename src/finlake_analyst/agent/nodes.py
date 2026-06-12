"""Factories dos nós do grafo LangGraph — cada factory injeta LLM/tool/prompt."""

from collections.abc import Awaitable, Callable

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from finlake_analyst.agent.state import AgentState
from finlake_analyst.tools.sql_execute import SqlExecuteTool

_ERROR_PREFIXES = ("SQL_ERROR:", "SECURITY_ERROR:")

_HANDLE_ERROR_MSG = (
    "Não consegui processar sua pergunta após múltiplas tentativas. "
    "O banco de dados financeiro pode não conter os dados necessários "
    "para responder essa consulta específica, ou a pergunta pode estar "
    "fora do escopo dos dados disponíveis — fundos de investimento CVM "
    "e indicadores macroeconômicos BCB (SELIC, IPCA, PTAX). "
    "Tente reformular a pergunta, especificar um período diferente "
    "ou consultar se os dados para esse período estão disponíveis."
)


def make_generate_sql_node(
    llm: ChatAnthropic,
    sql_prompt: ChatPromptTemplate,
) -> Callable[[AgentState], Awaitable[dict]]:
    """Cria o nó generate_sql com LLM e sql_prompt injetados.

    Em retry (retry_count > 0), inclui o SQL anterior e o erro no contexto
    da pergunta para que o Claude possa corrigir o SQL.
    """

    async def generate_sql(state: AgentState) -> dict:
        """Gera SQL a partir da pergunta. Inclui contexto de erro em retry."""
        question = state["question"]
        if state["retry_count"] > 0:
            question = (
                f"{question}\n\n"
                f"[Tentativa anterior falhou]\n"
                f"SQL gerado: {state['sql']}\n"
                f"Erro recebido: {state['error']}\n"
                f"Por favor, corrija o SQL para evitar o erro acima."
            )
        messages = sql_prompt.format_messages(question=question)
        response = await llm.ainvoke(messages)
        return {"sql": response.content.strip()}

    return generate_sql


def make_execute_sql_node(
    tool: SqlExecuteTool,
) -> Callable[[AgentState], Awaitable[dict]]:
    """Cria o nó execute_sql com SqlExecuteTool injetada.

    Incrementa retry_count quando o resultado contém prefixo de erro.
    """

    async def execute_sql(state: AgentState) -> dict:
        """Executa o SQL gerado e incrementa retry_count em caso de erro."""
        result = await tool._arun(state["sql"])
        if result.startswith(_ERROR_PREFIXES):
            return {
                "sql_result": result,
                "error": result,
                "retry_count": state["retry_count"] + 1,
            }
        return {"sql_result": result, "error": None}

    return execute_sql


def make_interpret_result_node(
    llm: ChatAnthropic,
    interpretation_prompt: ChatPromptTemplate,
) -> Callable[[AgentState], Awaitable[dict]]:
    """Cria o nó interpret_result com LLM e interpretation_prompt injetados."""

    async def interpret_result(state: AgentState) -> dict:
        """Gera análise financeira em português do resultado SQL."""
        messages = interpretation_prompt.format_messages(
            question=state["question"],
            sql=state["sql"],
            result=state["sql_result"],
        )
        response = await llm.ainvoke(messages)
        return {"analysis": response.content}

    return interpret_result


def handle_error(state: AgentState) -> dict:
    """Retorna mensagem de erro em português sem expor detalhes técnicos."""
    return {"analysis": _HANDLE_ERROR_MSG}
