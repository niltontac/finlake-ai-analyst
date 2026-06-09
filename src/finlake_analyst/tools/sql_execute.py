"""Tool LangChain para execução de queries SQL SELECT no banco Gold."""

import re

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from finlake_analyst.tools.database import get_database

_SELECT_RE = re.compile(r"^\s*(WITH\b.*\bSELECT\b|SELECT\b)", re.IGNORECASE | re.DOTALL)
_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_MAX_ROWS = 50


def _maybe_add_limit(query: str) -> str:
    """Adiciona LIMIT se a query não tiver um."""
    if not _LIMIT_RE.search(query):
        return f"{query.rstrip().rstrip(';')} LIMIT {_MAX_ROWS}"
    return query


class _SqlExecuteInput(BaseModel):
    query: str = Field(description="Query SQL SELECT a ser executada no banco Gold")


class SqlExecuteTool(BaseTool):
    """Executa queries SQL SELECT no banco Gold financeiro."""

    name: str = "execute_sql"
    description: str = (
        "Executa uma query SQL SELECT no banco de dados Gold financeiro. "
        "Tabelas disponíveis: macro_mensal, macro_diario (gold_bcb) e fundo_mensal (gold_cvm). "
        "Retorna os resultados com nomes de colunas. "
        "Apenas queries SELECT são permitidas. "
        "Se a query não tiver LIMIT, serão retornadas até 50 linhas automaticamente."
    )
    args_schema: type[BaseModel] = _SqlExecuteInput

    def _run(self, query: str) -> str:
        """Valida, executa e retorna resultado ou mensagem de erro."""
        if not _SELECT_RE.match(query):
            return "SECURITY_ERROR: Only SELECT queries are allowed."

        query = _maybe_add_limit(query)

        try:
            result = get_database().run(query, include_columns=True)
            return result or "Query executada com sucesso. Nenhum resultado retornado."
        except Exception as exc:
            return f"SQL_ERROR: {exc}"

    async def _arun(self, query: str) -> str:
        """Versão async — delega para _run."""
        return self._run(query)
