# DESIGN: AGENT_CORE

> Especificação técnica do grafo LangGraph que orquestra SQL_TOOL + PROMPTS + Claude para responder perguntas financeiras em português.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | AGENT_CORE |
| **Data** | 2026-06-11 |
| **Autor** | Nilton Coura |
| **Status** | ✅ Shipped |
| **DEFINE** | [DEFINE_AGENT_CORE.md](DEFINE_AGENT_CORE.md) |

---

## Diagrama de Arquitetura

```
Chainlit on_chat_start
    │
    ├── SqlSchemaTool()._run("")  → schema (str)
    ├── get_sql_prompt().partial(schema=schema) → sql_prompt (ChatPromptTemplate)
    └── create_agent_graph(sql_prompt) → graph (CompiledStateGraph)
                │
                └── [armazenado em cl.user_session]

Chainlit on_message
    │
    ├── graph = cl.user_session.get("graph")
    ├── initial_state = {question, sql="", sql_result="", retry_count=0, error=None, analysis=""}
    │
    └── graph.astream_events(initial_state, version="v2")
                │
                ▼
         ┌─────────────────────────────────────────────────┐
         │                 StateGraph                       │
         │                                                  │
         │   START                                          │
         │     │                                            │
         │     ▼                                            │
         │ [generate_sql]  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐   │
         │     │  ChatAnthropic.ainvoke(sql_prompt)    │   │
         │     │  returns: {sql: "SELECT ..."}         │   │
         │     ▼                                       │   │
         │ [execute_sql]                               │   │
         │     │  SqlExecuteTool._arun(sql)            │   │
         │     │  returns: {sql_result, error,         │   │
         │     │            retry_count+1 if error}    │   │
         │     │                                       │   │
         │     └──── SQL_ERROR? ────────────────────── ┤   │
         │           │              retry_count < 2  ──┘   │
         │           │              (back to generate_sql)  │
         │           │                                      │
         │           └── retry_count >= 2                   │
         │                     │                            │
         │                     ▼                            │
         │               [handle_error]                     │
         │                     │  static msg in PT          │
         │                     ▼                            │
         │                    END                           │
         │                                                  │
         │     (success path)                               │
         │     │                                            │
         │     ▼                                            │
         │ [interpret_result]  ← streaming tokens →        │
         │     │  ChatAnthropic.ainvoke(interpretation)     │
         │     │  returns: {analysis: "..."}                │
         │     ▼                                            │
         │    END                                           │
         └─────────────────────────────────────────────────┘
                │
                └── astream_events filters:
                    on_chat_model_stream + langgraph_node="interpret_result"
                    → cl.Message.stream_token(chunk.content)
```

---

## Decisões de Arquitetura (ADRs Inline)

### ADR-001: Closures (node factories) para injeção de dependência nos nós

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-11 |

**Contexto:** Os nós `generate_sql` e `interpret_result` precisam de acesso ao LLM e aos prompts. LangGraph node functions têm a assinatura `(state) -> dict` — sem parâmetros adicionais. Os nós precisam ser testáveis com mocks injetados.

**Decisão:** Factory functions (`make_generate_sql_node`, `make_execute_sql_node`, `make_interpret_result_node`) retornam closures que capturam LLM, prompts e tools.

**Rationale:** Permite injeção de mocks nos testes sem `patch`. A assinatura do LangGraph `(state) -> dict` é preservada. Cada nó é testado em isolamento com `AsyncMock`.

**Alternativas Rejeitadas:**
1. `functools.partial` — legível mas menos flexível para múltiplos argumentos
2. Classe `AgentNodes` com métodos — overhead de classe para um grupo de funções sem estado compartilhado

**Consequências:**
- `create_agent_graph()` chama as factories internamente
- Testes instanciam as factories diretamente com mocks

---

### ADR-002: `retry_count` incrementado em `execute_sql`

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-11 |

**Contexto:** É necessário rastrear tentativas falhadas e parar com `>= 2`. Duas opções: incrementar em `execute_sql` (quando detecta o erro) ou em `generate_sql` (antes de cada tentativa).

**Decisão:** Incrementar `retry_count` em `execute_sql` quando o resultado contém `SQL_ERROR:` ou `SECURITY_ERROR:`.

**Rationale:** O `execute_sql` é o único nó que sabe se a tentativa falhou. Incrementar ali mantém a lógica causal. O edge condicional `_route_after_execute` lê `state["retry_count"]` já incrementado.

**Consequências:**
- `retry_count = 1` = primeira falha (cota disponível: mais 1 retry)
- `retry_count = 2` = segunda falha → `handle_error` (AT-006 confirmado)
- `generate_sql` no retry usa `state["retry_count"] > 0` para injetar contexto de erro

---

### ADR-003: Streaming filtrado por `langgraph_node == "interpret_result"`

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-11 |

**Contexto:** `.astream_events(version="v2")` emite `on_chat_model_stream` para TODOS os nós que chamam LLM — incluindo `generate_sql`. Expor o SQL gerado ao usuário viola a UX definida.

**Decisão:** Filtrar `event["metadata"].get("langgraph_node") == "interpret_result"` antes de chamar `stream_token()`. SQL gerado é detalhe interno.

**Assumptions a validar no Build:**
- A-001: `ChatAnthropic.ainvoke()` dentro de nó LangGraph emite `on_chat_model_stream` via `astream_events(version="v2")`
- A-002: `event["metadata"]["langgraph_node"]` está disponível nesses eventos

**Alternativas Rejeitadas:**
1. Usar `on_llm_new_token` — event name instável entre versões LangChain
2. Filtrar por tag — mais verboso, sem ganho em clareza

---

### ADR-004: `handle_error` sync + captura via `on_chain_end`

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-11 |

**Contexto:** `handle_error` não faz I/O — retorna string estática. Quando `handle_error` é atingido, nenhum `on_chat_model_stream` é emitido, então `msg.content` fica vazio.

**Decisão:** `handle_error` é função sync. `app.py` captura o output do nó via `on_chain_end` com `event["name"] == "handle_error"`, guardando o `analysis` numa variável `error_fallback`. Após o loop de events, se `msg.content` está vazio e `error_fallback` não, usa `error_fallback` como conteúdo da mensagem.

**Rationale:** Evita rodar o grafo duas vezes. LangGraph v2 emite `on_chain_end` com o dict retornado pelo nó.

**Consequências:**
- Precisa de teste manual para validar no Build (assumptions A-001/A-002)
- Se `on_chain_end` não contiver o output esperado, fallback para mensagem genérica hardcoded

---

## File Manifest

| # | Arquivo | Ação | Propósito | Dependências |
|---|---|---|---|---|
| 1 | `src/finlake_analyst/agent/state.py` | Criar | `AgentState` TypedDict | Nenhuma |
| 2 | `src/finlake_analyst/agent/nodes.py` | Criar | Factories dos 4 nós | 1 |
| 3 | `src/finlake_analyst/agent/graph.py` | Criar | StateGraph + `create_agent_graph()` | 1, 2 |
| 4 | `src/finlake_analyst/agent/__init__.py` | Modificar | Re-exporta `create_agent_graph` | 3 |
| 5 | `src/finlake_analyst/app.py` | Modificar | Integração Chainlit com streaming | 3, 4 |
| 6 | `tests/test_agent_nodes.py` | Criar | Testes unitários dos nós com mocks | 1, 2 |
| 7 | `tests/test_agent_graph.py` | Criar | Testes do grafo e routing | 1, 3 |

---

## Code Patterns

### Arquivo 1 — `src/finlake_analyst/agent/state.py`

```python
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
```

---

### Arquivo 2 — `src/finlake_analyst/agent/nodes.py`

```python
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
```

---

### Arquivo 3 — `src/finlake_analyst/agent/graph.py`

```python
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
    llm = ChatAnthropic(
        model=settings.model_name,
        api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
    )
    tool = SqlExecuteTool()
    interpretation_prompt = get_interpretation_prompt()

    generate_sql = make_generate_sql_node(llm, sql_prompt)
    execute_sql = make_execute_sql_node(tool)
    interpret_result = make_interpret_result_node(llm, interpretation_prompt)

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
```

> **Nota sobre `api_key`:** `ChatAnthropic` espera `SecretStr` para `api_key`. O `# type: ignore[arg-type]` suprime o warning do mypy pois a biblioteca aceita `str` em runtime. Alternativa: `SecretStr(settings.anthropic_api_key)`.

---

### Arquivo 4 — `src/finlake_analyst/agent/__init__.py`

```python
"""Módulo do agente LangGraph — grafo Text-to-SQL stateful."""

from finlake_analyst.agent.graph import create_agent_graph

__all__ = ["create_agent_graph"]
```

---

### Arquivo 5 — `src/finlake_analyst/app.py`

```python
"""Entry point Chainlit do finlake-analyst.

Executar com:
    uv run chainlit run src/finlake_analyst/app.py --watch
"""

import chainlit as cl

from finlake_analyst.agent import create_agent_graph
from finlake_analyst.agent.state import AgentState
from finlake_analyst.config import get_settings
from finlake_analyst.prompts import get_sql_prompt
from finlake_analyst.tools.sql_schema import SqlSchemaTool

_settings = get_settings()


@cl.on_chat_start
async def on_chat_start() -> None:
    """Inicializa sessão — injeta schema, compila grafo e armazena na sessão."""
    schema = SqlSchemaTool()._run("")
    sql_prompt = get_sql_prompt().partial(schema=schema)
    graph = create_agent_graph(sql_prompt)
    cl.user_session.set("graph", graph)
    await cl.Message(
        content=(
            "Olá! Sou o **FinLake Analyst**, seu assistente para análise de "
            "dados financeiros brasileiros.\n\n"
            "Faça uma pergunta sobre fundos de investimento ou indicadores "
            "macroeconômicos (SELIC, IPCA, PTAX).\n\n"
            f"_Modelo: {_settings.model_name}_"
        ),
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Processa pergunta do usuário via grafo LangGraph com streaming."""
    graph = cl.user_session.get("graph")

    initial_state: AgentState = {
        "question": message.content,
        "sql": "",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }

    msg = cl.Message(content="")
    error_fallback = ""

    async for event in graph.astream_events(initial_state, version="v2"):
        kind = event["event"]
        node = event["metadata"].get("langgraph_node", "")

        if kind == "on_chat_model_stream" and node == "interpret_result":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                await msg.stream_token(chunk.content)

        elif kind == "on_chain_end" and event.get("name") == "handle_error":
            output = event["data"].get("output", {})
            if isinstance(output, dict):
                error_fallback = output.get("analysis", "")

    if not msg.content and error_fallback:
        msg.content = error_fallback

    await msg.send()
```

---

### Arquivo 6 — `tests/test_agent_nodes.py`

> `asyncio_mode = "auto"` já está configurado em `pyproject.toml` — sem necessidade de `@pytest.mark.asyncio`.

```python
"""Testes unitários dos nós do agente — sem banco ou API real."""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
```

---

### Arquivo 7 — `tests/test_agent_graph.py`

```python
"""Testes do grafo LangGraph — compilação e lógica de routing."""

from unittest.mock import MagicMock, patch

import pytest

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
```

---

## Testing Strategy

| Tipo | Escopo | Arquivo | Ferramentas |
|---|---|---|---|
| Unit — nós | Cada factory function em isolamento com `AsyncMock` | `test_agent_nodes.py` | pytest, AsyncMock, MagicMock |
| Unit — routing | `_route_after_execute()` com estados construídos | `test_agent_graph.py` | pytest (sync) |
| Unit — compilação | `create_agent_graph()` com LLM e settings mockados | `test_agent_graph.py` | patch, MagicMock |
| Smoke (manual) | Pergunta end-to-end via Chainlit UI | — | uv run chainlit |

### Validação das Assumptions no início do Build

Antes de escrever `app.py`, rodar este script de validação rápida (requer `.env` com credenciais reais):

```python
# Smoke test de streaming — validar A-001 e A-002
# Executar com: uv run python -c "import asyncio; from validate_streaming import run; asyncio.run(run())"
import asyncio
from finlake_analyst.agent import create_agent_graph
from finlake_analyst.agent.state import AgentState
from finlake_analyst.prompts import get_sql_prompt
from finlake_analyst.tools.sql_schema import SqlSchemaTool

async def run() -> None:
    schema = SqlSchemaTool()._run("")
    sql_prompt = get_sql_prompt().partial(schema=schema)
    graph = create_agent_graph(sql_prompt)

    initial_state: AgentState = {
        "question": "Qual a taxa SELIC no último mês disponível?",
        "sql": "", "sql_result": "", "retry_count": 0,
        "error": None, "analysis": "",
    }

    stream_events_seen = []
    async for event in graph.astream_events(initial_state, version="v2"):
        if event["event"] == "on_chat_model_stream":
            node = event["metadata"].get("langgraph_node", "N/A")
            stream_events_seen.append(node)
            print(f"  on_chat_model_stream  node={node}")

    print(f"\nNodes with streaming: {set(stream_events_seen)}")
    print("A-001 OK:", len(stream_events_seen) > 0)
    print("A-002 OK:", all(n != "N/A" for n in stream_events_seen))
```

---

## Considerações de Segurança

- `SqlExecuteTool._run()` já valida `SELECT` via regex — SECURITY_ERROR retornado, nunca executado
- `anthropic_api_key` lido de `Settings` via `.env` — nunca hardcoded
- `cl.user_session` isolado por sessão Chainlit — grafos não são compartilhados entre usuários
- SQL gerado nunca exibido ao usuário — filtro `langgraph_node == "interpret_result"` em `app.py`

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-11 | Nilton Coura | Versão inicial a partir de DEFINE_AGENT_CORE.md |
| 1.1 | 2026-06-12 | ship-agent | Shipped and archived |

---

## Next Step

**Pronto para:** `/build .claude/sdd/features/DESIGN_AGENT_CORE.md`
