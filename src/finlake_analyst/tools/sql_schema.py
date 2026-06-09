"""Tool LangChain para inspeção de schema das tabelas Gold."""

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from finlake_analyst.tools.database import get_database

_DATA_QUALITY_NOTES = """
NOTAS DE QUALIDADE DOS DADOS:
- Campo 'gestor' em fundo_mensal é nulo na maioria dos registros (limitação da fonte CVM)
- Filtrar rentabilidade_mes_pct < 1000 em queries de ranking (outliers por erro de cadastro CVM)
- alpha_selic e alpha_ipca disponíveis apenas até 2024-12 (cross-domain BCB pendente para 2025+)
- Tabela gold_cvm.fundo_diario NÃO está disponível — usar fundo_mensal para análises conversacionais
"""


class _SqlSchemaInput(BaseModel):
    table_names: str = Field(
        default="",
        description=(
            "Nomes das tabelas separados por vírgula "
            "(ex: 'fundo_mensal,macro_mensal'). "
            "Vazio retorna schema de todas as tabelas disponíveis."
        ),
    )


class SqlSchemaTool(BaseTool):
    """Retorna schema, amostras e notas de qualidade das tabelas Gold."""

    name: str = "get_schema"
    description: str = (
        "Retorna o schema (colunas, tipos, linhas de amostra) das tabelas Gold disponíveis. "
        "Tabelas: macro_mensal, macro_diario (gold_bcb) e fundo_mensal (gold_cvm). "
        "Use antes de gerar SQL para entender a estrutura e colunas disponíveis. "
        "Inclui notas de qualidade dos dados (campos nulos, outliers, limitações)."
    )
    args_schema: type[BaseModel] = _SqlSchemaInput

    def _run(self, table_names: str = "") -> str:
        """Retorna schema das tabelas solicitadas + notas de qualidade."""
        tables = [t.strip() for t in table_names.split(",") if t.strip()] or None
        schema = get_database().get_table_info(table_names=tables)
        return f"{schema}\n{_DATA_QUALITY_NOTES}"

    async def _arun(self, table_names: str = "") -> str:
        """Versão async — delega para _run."""
        return self._run(table_names)
