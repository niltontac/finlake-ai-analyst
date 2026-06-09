# DESIGN: SQL_TOOL

> Design técnico das duas LangChain tools que conectam o agente LangGraph ao PostgreSQL Gold.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | SQL_TOOL |
| **Data** | 2026-06-09 |
| **Autor** | Nilton Coura |
| **DEFINE** | [DEFINE_SQL_TOOL.md](./DEFINE_SQL_TOOL.md) |
| **Status** | ✅ Shipped |

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                     SQL_TOOL — Fluxo de dados                        │
│                                                                       │
│   LangGraph Agent                                                     │
│         │                                                             │
│         ├──▶ execute_sql(query: str)                                  │
│         │         │                                                   │
│         │         ├── [1] SELECT validation                           │
│         │         │       └── non-SELECT → "SECURITY_ERROR: ..."     │
│         │         │                                                   │
│         │         ├── [2] auto-LIMIT (se não tiver LIMIT)            │
│         │         │       └── query + " LIMIT 50"                    │
│         │         │                                                   │
│         │         └── [3] get_database().run(query, include_columns) │
│         │                     │                                       │
│         │                 ┌───┴───────────────────────────────┐      │
│         │                 │  PostgreSQL :5433                  │      │
│         │                 │  engine search_path=               │      │
│         │                 │    gold_bcb,gold_cvm               │      │
│         │                 │                                    │      │
│         │                 │  Tables exposed:                   │      │
│         │                 │  ├── macro_mensal  (gold_bcb)      │      │
│         │                 │  ├── macro_diario  (gold_bcb)      │      │
│         │                 │  └── fundo_mensal  (gold_cvm)      │      │
│         │                 └───────────────────────────────────┘      │
│         │                                                             │
│         │         ┌── OK → string com dados (tuple format + colunas) │
│         │         └── Erro SQL → "SQL_ERROR: <mensagem PostgreSQL>"  │
│         │                                                             │
│         └──▶ get_schema(table_names: str)                             │
│                   │                                                   │
│                   └── get_database().get_table_info(tables)           │
│                               + DATA_QUALITY_NOTES                   │
│                               → DDL + 3 linhas amostra + notas       │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components

| Componente | Propósito | Tecnologia |
|---|---|---|
| `database.py` | Singleton `SQLDatabase` com multi-schema PostgreSQL | SQLAlchemy + langchain-community |
| `sql_execute.py` | `SqlExecuteTool` — valida SELECT, executa, retorna resultado ou erro | LangChain `BaseTool` |
| `sql_schema.py` | `SqlSchemaTool` — retorna schema + amostras + notas de qualidade | LangChain `BaseTool` |
| `tools/__init__.py` | Exporta ambas as tools para consumo pelo `agent/` | Python package |

---

## Key Decisions

### Decisão 1: Multi-schema via `search_path` no SQLAlchemy engine

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-09 |

**Contexto:** `SQLDatabase.__init__` aceita apenas um `schema` por instância. O banco Gold usa dois schemas distintos: `gold_bcb` (macro) e `gold_cvm` (fundos). Verificado na inspeção do código-fonte `langchain_community==0.4.2`.

**Escolha:** Criar o SQLAlchemy `Engine` com `connect_args={"options": "-c search_path=gold_bcb,gold_cvm"}` e passar para `SQLDatabase(engine=..., schema=None)`. Assim `SQLDatabase` usa `inspector.get_table_names(schema=None)` que retorna tabelas do `search_path` ativo.

**Rationale:** O `search_path` do PostgreSQL faz a resolução de nomes sem prefixo de schema funcionar corretamente. As tabelas não têm nomes conflitantes entre os dois schemas (`macro_*` é BCB, `fundo_*` é CVM), então não há ambiguidade.

**Alternativas rejeitadas:**
1. **Duas instâncias `SQLDatabase`** (uma por schema) — complicaria a interface da tool, que precisaria escolher qual instância usar por tabela
2. **Schema qualificado em `include_tables`** (`"gold_bcb.macro_mensal"`) — o inspector SQLAlchemy usa `schema=` separado, não nome qualificado na lista de tabelas

**Consequências:**
- O LLM pode gerar SQL sem prefixo de schema (ex: `FROM fundo_mensal`) — funciona via `search_path`
- Em testes, mockar `get_database()` no ponto de uso (não no `lru_cache`)

---

### Decisão 2: `langchain-community` mantido apesar da deprecação

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-09 |

**Contexto:** `langchain-community` exibiu `DeprecationWarning` no ambiente instalado (v0.4.2): *"langchain-community is being sunset"*. O `SQLDatabase` não tem substituto standalone confirmado no ecossistema LangChain atual.

**Escolha:** Manter `langchain-community` para v1. O código está isolado em `tools/database.py` — a troca futura requer mudança em um único arquivo.

**Rationale:** O pacote ainda funciona na versão instalada. A migration guidance indica standalone packages por integração, mas `SQLDatabase` é uma utilitária genérica sem substituto óbvio ainda. A alternativa (SQLAlchemy direto) reimplementa `get_table_info` e row formatting desnecessariamente.

**Alternativas rejeitadas:**
1. **SQLAlchemy direto** — reimplementa ~100 linhas de `get_table_info` com DDL e amostras que `SQLDatabase` já oferece
2. **Bloquear a feature** aguardando substituto — YAGNI; o código de produção pode usar `langchain-community` com warning suprimido

**Consequências:**
- Monitorar issues do LangChain sobre replacement de `SQLDatabase`; migrar em feature `INFRA_UPDATE` quando disponível
- `warnings.filterwarnings` pode ser necessário para suprimir o warning em logs de produção

---

### Decisão 3: Validação SELECT por regex, não parser SQL

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-09 |

**Contexto:** Precisamos rejeitar DDL e DML. SQL com CTEs (`WITH ... AS (...) SELECT ...`) começa com `WITH`, não `SELECT`.

**Escolha:** Regex `r'^\s*(WITH\b.*\bSELECT\b|SELECT\b)'` com `re.IGNORECASE | re.DOTALL`. Aceita `SELECT` puro e CTEs que terminam em `SELECT`.

**Rationale:** Parser SQL completo é YAGNI. O LLM treinado para Text-to-SQL gera queries analíticas — CTEs com SELECT final ou SELECT direto. O regex cobre os dois casos. Comandos `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE` não passam no padrão.

**Alternativas rejeitadas:**
1. **Verificar se começa com `SELECT`** — rejeita CTEs válidas
2. **Parser SQL completo** (`sqlparse`, `sqlglot`) — overhead desnecessário para v1

**Consequências:**
- `WITH cte AS (SELECT ...) SELECT * FROM cte` — aceito ✓
- `WITH RECURSIVE ...` — aceito (começa com WITH, contém SELECT) ✓
- `SELECT INTO ...` (PostgreSQL) — aceito (começa com SELECT); inofensivo pois requer privilégios de criação

---

### Decisão 4: `include_columns=True` no `SQLDatabase.run()`

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-09 |

**Contexto:** `SQLDatabase.run()` retorna os dados como string de tuplas `[(val1, val2), ...]`. Sem nomes de colunas, o LLM perde contexto para interpretar os valores.

**Escolha:** Usar `db.run(query, include_columns=True)` para incluir nomes de colunas no output.

**Rationale:** Com `include_columns=True`, o output inclui os nomes das colunas antes dos dados. O LLM consegue associar `taxa_anual` ao valor `11.75` e gerar uma resposta financeira correta em português.

**Alternativas rejeitadas:**
1. **Conversão para markdown table** — implementação adicional desnecessária; o LLM interpreta o formato nativo do `SQLDatabase` perfeitamente
2. **JSON list of dicts** — mais tokens, sem ganho de acurácia para o caso de uso

**Consequências:**
- Output levemente mais verboso (nomes de colunas repetidos), mas dentro do limite de contexto para queries com `LIMIT 50`

---

### Decisão 5: auto-LIMIT via `_maybe_add_limit()` em `sql_execute.py`

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-09 |

**Contexto:** Queries sem `LIMIT` podem retornar milhares de linhas, estourando o contexto do LLM e degradando a resposta.

**Escolha:** Se a query não contém `LIMIT` (case-insensitive), a função `_maybe_add_limit()` adiciona `LIMIT 50` antes da execução.

**Rationale:** Simples, previsível, documentado na `description` da tool para o LLM saber que vai acontecer. Não afeta queries que já têm `LIMIT`. Não afeta `COUNT(*)` e outras aggregações (que retornam 1 linha de qualquer forma).

**Alternativas rejeitadas:**
1. **`max_string_length` do `SQLDatabase`** — trunca a string de resultado, não o número de linhas. Pode retornar dados corrompidos no meio de uma linha
2. **`fetch="many"` com `cursor.arraysize`** — controle menos previsível; depende do driver

**Consequências:**
- Queries de ranking sem LIMIT sempre retornam até 50 — comportamento esperado para queries conversacionais

---

## File Manifest

| # | Arquivo | Ação | Propósito | Dependências |
|---|---|---|---|---|
| 1 | `src/finlake_analyst/tools/database.py` | Create | `get_database()` singleton com SQLAlchemy engine multi-schema | `config.py` |
| 2 | `src/finlake_analyst/tools/sql_execute.py` | Create | `SqlExecuteTool` — validação SELECT, auto-LIMIT, execução | 1 |
| 3 | `src/finlake_analyst/tools/sql_schema.py` | Create | `SqlSchemaTool` — schema DDL + amostras + notas de qualidade | 1 |
| 4 | `src/finlake_analyst/tools/__init__.py` | Modify | Exportar `SqlExecuteTool`, `SqlSchemaTool` | 2, 3 |
| 5 | `tests/test_sql_execute.py` | Create | 6 testes de `SqlExecuteTool` com mock de `get_database` | 2 |
| 6 | `tests/test_sql_schema.py` | Create | 3 testes de `SqlSchemaTool` com mock de `get_database` | 3 |

**Total:** 6 arquivos (2 modificados, 4 novos)

---

## Agent Assignment Rationale

| Agente | Arquivos | Motivo |
|---|---|---|
| @python-developer | 1, 2, 3, 4 | Código Python com BaseTool, pydantic, type hints |
| @test-generator | 5, 6 | Testes pytest com mocks e fixtures |

---

## Code Patterns

### Pattern 1: `database.py` — SQLDatabase singleton multi-schema

```python
# src/finlake_analyst/tools/database.py
"""Singleton SQLDatabase com acesso multi-schema ao PostgreSQL Gold."""

from functools import lru_cache

from langchain_community.utilities import SQLDatabase
from sqlalchemy import create_engine

from finlake_analyst.config import get_settings

_EXPOSED_TABLES: list[str] = ["macro_mensal", "macro_diario", "fundo_mensal"]


def _create_engine(database_url: str):
    """Cria engine SQLAlchemy com search_path para acesso multi-schema."""
    return create_engine(
        database_url,
        connect_args={"options": "-c search_path=gold_bcb,gold_cvm"},
    )


@lru_cache(maxsize=1)
def get_database() -> SQLDatabase:
    """Retorna instância singleton de SQLDatabase conectada ao Gold PostgreSQL."""
    settings = get_settings()
    engine = _create_engine(settings.database_url)
    return SQLDatabase(
        engine=engine,
        include_tables=_EXPOSED_TABLES,
        sample_rows_in_table_info=3,
    )
```

---

### Pattern 2: `sql_execute.py` — SqlExecuteTool

```python
# src/finlake_analyst/tools/sql_execute.py
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
        """Versão async — delega para _run (I/O bound, sem bloqueio crítico em v1)."""
        return self._run(query)
```

---

### Pattern 3: `sql_schema.py` — SqlSchemaTool

```python
# src/finlake_analyst/tools/sql_schema.py
"""Tool LangChain para inspeção de schema das tabelas Gold."""

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from finlake_analyst.tools.database import get_database

_DATA_QUALITY_NOTES = """
NOTAS DE QUALIDADE DOS DADOS:
- Campo 'gestor' em fundo_mensal é nulo na maioria dos registros (limitação da fonte CVM)
- Filtrar rentabilidade_mes_pct < 1000 em queries de ranking (outliers por erro de cadastro CVM)
- Campos alpha_selic e alpha_ipca disponíveis apenas até 2024-12 (cross-domain BCB pendente para 2025+)
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
```

---

### Pattern 4: `tools/__init__.py` atualizado

```python
# src/finlake_analyst/tools/__init__.py
"""LangChain tools para execução SQL — implementadas na feature SQL_TOOL."""

from finlake_analyst.tools.sql_execute import SqlExecuteTool
from finlake_analyst.tools.sql_schema import SqlSchemaTool

__all__ = ["SqlExecuteTool", "SqlSchemaTool"]
```

---

### Pattern 5: `tests/test_sql_execute.py`

```python
# tests/test_sql_execute.py
"""Testes de SqlExecuteTool com mock de SQLDatabase."""

from unittest.mock import MagicMock, patch

import pytest

from finlake_analyst.tools.sql_execute import SqlExecuteTool, _maybe_add_limit

_MOCK_RESULT = "date|taxa_anual\n2024-01-01|11.75\n2024-02-01|11.25"


@pytest.fixture()
def tool() -> SqlExecuteTool:
    return SqlExecuteTool()


@pytest.fixture()
def mock_db():
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


# --- unit tests for _maybe_add_limit ---

def test_maybe_add_limit_adds_when_absent() -> None:
    assert "LIMIT 50" in _maybe_add_limit("SELECT 1")


def test_maybe_add_limit_preserves_existing() -> None:
    q = "SELECT 1 LIMIT 10"
    assert _maybe_add_limit(q) == q
```

---

### Pattern 6: `tests/test_sql_schema.py`

```python
# tests/test_sql_schema.py
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
def mock_db():
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
    """Nomes de tabelas são passados para get_table_info."""
    tool._run("fundo_mensal,macro_mensal")
    mock_db.get_table_info.assert_called_once_with(
        table_names=["fundo_mensal", "macro_mensal"]
    )
```

---

## Data Flow

```text
1. LangGraph agent recebe pergunta financeira do usuário
   │
   ▼
2. Agent chama get_schema() para entender as tabelas
   │
   ▼
3. SqlSchemaTool.run() → get_database().get_table_info() → DDL + amostras + notas
   │
   ▼
4. Agent gera SQL baseado no schema + contexto da pergunta
   │
   ▼
5. Agent chama execute_sql(query)
   │
   ├── SELECT? → _maybe_add_limit() → get_database().run(include_columns=True)
   │                                        │
   │                                  PostgreSQL :5433 (search_path=gold_bcb,gold_cvm)
   │                                        │
   │                             OK → dados com colunas (string)
   │                             Erro → "SQL_ERROR: <mensagem>"
   │
   └── Non-SELECT? → "SECURITY_ERROR: ..."
   │
   ▼
6. Agent interpreta resultado e gera resposta em português
   │
   ▼
7. LangFuse rastreia o trace (configurado em OBSERVABILITY)
```

---

## Integration Points

| Sistema | Tipo | Auth | Arquivo |
|---|---|---|---|
| PostgreSQL :5433 | SQLAlchemy + psycopg2 | `DATABASE_URL` via `Settings` | `database.py` |
| LangChain SQLDatabase | Python SDK (langchain-community) | N/A (local) | `database.py` |
| LangGraph agent | Consome as tools via `tools/__init__.py` | N/A (internal) | `tools/__init__.py` |

---

## Testing Strategy

| Tipo | Escopo | Arquivo | Ferramentas | Meta |
|---|---|---|---|---|
| Unit | `SqlExecuteTool._run()` | `tests/test_sql_execute.py` | pytest + unittest.mock | 8 testes: SELECT, SECURITY, SQL_ERROR, auto-LIMIT, CTE, `_maybe_add_limit` |
| Unit | `SqlSchemaTool._run()` | `tests/test_sql_schema.py` | pytest + unittest.mock | 3 testes: schema, notas, table_names forwarding |
| Manual | Conexão PostgreSQL real | — | `uv run python -c "..."` | Verificar `get_database()` conecta e lista tabelas |

**Todos os testes unitários usam mock — não requerem PostgreSQL rodando.**

---

## Error Handling

| Erro | Estratégia | Arquivo |
|---|---|---|
| Non-SELECT (DELETE, UPDATE, DROP) | `SECURITY_ERROR: Only SELECT queries are allowed.` | `sql_execute.py` |
| SQL inválido / tabela inexistente | `SQL_ERROR: <mensagem PostgreSQL>` via `except Exception` | `sql_execute.py` |
| Conexão PostgreSQL falha | `lru_cache` preserva tentativa; nova chamada tenta reconectar | `database.py` |
| `table_names` inválido em `get_schema` | `SQLDatabase.get_table_info` levanta `ValueError` — propaga para o agente como erro de tool | `sql_schema.py` |

---

## Configuration

| Key | Tipo | Default | Origem |
|---|---|---|---|
| `DATABASE_URL` | str | required | `Settings` via `.env` |
| `_EXPOSED_TABLES` | list[str] | `["macro_mensal", "macro_diario", "fundo_mensal"]` | Constante em `database.py` |
| `_MAX_ROWS` | int | `50` | Constante em `sql_execute.py` |
| `sample_rows_in_table_info` | int | `3` | Constante em `database.py` |

---

## Security Considerations

- Apenas `SELECT` e CTEs com `SELECT` final são executados — regex `_SELECT_RE` bloqueia DDL/DML
- `get_database()` usa `DATABASE_URL` de `Settings` — nunca hardcoded
- Em produção: criar usuário PostgreSQL com `GRANT SELECT ON ALL TABLES IN SCHEMA gold_bcb, gold_cvm` — documentado no `CLAUDE.md`
- `search_path` limitado a `gold_bcb,gold_cvm` — agente não tem acesso a outros schemas

---

## Observability

| Aspecto | Implementação na SQL_TOOL |
|---|---|
| Logging | Erros retornados como string — visíveis no trace LangFuse (feature OBSERVABILITY) |
| Tracing | Tools LangChain são rastreadas automaticamente pelo LangFuse CallbackHandler |
| Query audit | `SQL_ERROR:` e `SECURITY_ERROR:` no trace permitem auditoria de queries rejeitadas |

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-09 | Nilton Coura | Versão inicial; resolve A-001 (multi-schema via search_path) |

---

## Next Step

**Pronto para:** `/build .claude/sdd/features/DESIGN_SQL_TOOL.md`
