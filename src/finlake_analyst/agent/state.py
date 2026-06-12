"""AgentState TypedDict — estado compartilhado do grafo LangGraph."""

from typing import TypedDict


class AgentState(TypedDict):
    """Estado do agente Text-to-SQL — propagado entre todos os nós do grafo."""

    question: str        # pergunta original do usuário
    sql: str             # SQL gerado (última versão; vazio na entrada)
    sql_result: str      # resultado do SqlExecuteTool ou "SQL_ERROR:..." / "SECURITY_ERROR:..."
    retry_count: int     # tentativas falhadas: 0=nenhuma, 1=primeira falha, 2=segunda falha
    error: str | None    # último erro para contexto no retry; None em sucesso
    analysis: str        # análise financeira final (output de interpret_result ou handle_error)
