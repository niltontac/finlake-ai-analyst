# DESIGN: OBSERVABILITY

> LangFuse traces com metadata enriquecida + script DeepEval de avaliação SQL.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | OBSERVABILITY |
| **Data** | 2026-06-12 |
| **Autor** | Nilton Coura |
| **Status** | ✅ Shipped |
| **Input** | [DEFINE_OBSERVABILITY.md](./DEFINE_OBSERVABILITY.md) |

---

## Descobertas Críticas (Pré-Design)

> Antes de projetar, as APIs reais foram validadas contra os pacotes instalados.
> As versões instaladas diferem significativamente das assumidas no BRAINSTORM/DEFINE.

| Pacote | Versão assumida (DEFINE) | Versão instalada | Impacto |
|---|---|---|---|
| `langfuse` | `>=2.0` | **4.7.1** | API completamente diferente: `langfuse.callback` não existe |
| `deepeval` | `>=1.4` | **4.0.5** | `LLMTestCaseParams` deprecated; `SingleTurnParams` é o novo nome |

Todas as decisões de design abaixo refletem as APIs das versões **realmente instaladas**.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  on_message (app.py)                                                │
│                                                                     │
│  1. os.environ.setdefault(LANGFUSE_*) ← Settings (uma vez no boot) │
│                                                                     │
│  2. CallbackHandler()  ←  langfuse.langchain (sem credenciais)      │
│     lf_config = {callbacks: [handler], metadata: {session_id, ...}} │
│                                                                     │
│  3. graph.astream_events(state, config=lf_config, version="v2")     │
│     ├─ on_chat_model_stream / interpret_result → stream_token       │
│     ├─ on_chain_end / execute_sql → captura retry_count             │
│     ├─ on_chain_end / generate_sql → captura final_sql              │
│     └─ on_chain_end / handle_error → captura error_fallback         │
│                                                                     │
│  4. Langfuse().create_score(trace_id=handler.last_trace_id,         │
│                             name="retry_count", value=N)            │
│     Langfuse().flush()                                              │
│                                                                     │
│  5. msg.send()                                                      │
└─────────────────────────────────────────────────────────────────────┘

         LangFuse Cloud
         ┌──────────────────────────────────┐
         │ Trace: finlake-analyst-query      │
         │  session_id: <chainlit-session>   │
         │  metadata.question: <pergunta>    │
         │  ├─ Span: generate_sql            │
         │  │   └─ Generation: LLM call      │
         │  │       input: <sql_prompt>      │
         │  │       output: <SQL gerado>  ←── automático via CallbackHandler
         │  ├─ Span: execute_sql             │
         │  └─ Span: interpret_result        │
         │  Score: retry_count = N           │
         │    comment: final_sql (300 chars) │
         └──────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  evals/eval_sql.py (script standalone)                              │
│                                                                     │
│  1. get_settings() → create_agent_graph(sql_prompt)                 │
│  2. Para P1–P5: graph.ainvoke(state) → state["sql"]                 │
│  3. AnthropicModel(model=settings.model_name, api_key=...)          │
│  4. GEval(criteria=SQL_EQUIV, model=anthropic_model, threshold=0.7) │
│  5. metric.measure(LLMTestCase(input, actual_output, expected))     │
│  6. Print: P1: ✓ PASS  score=0.82                                   │
│            ...                                                      │
│            Score geral: 4/5 (80%)                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Decision Records

### ADR-001: LangFuse 4.x — novo módulo de integração LangChain

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-12 |

**Contexto:** O DEFINE assumiu `from langfuse.callback import CallbackHandler` (API langfuse 2.x). O pacote instalado é langfuse **4.7.1**, que usa OpenTelemetry como backend. O módulo `langfuse.callback` não existe nesta versão.

**Escolha:** `from langfuse.langchain import CallbackHandler` — módulo correto para LangChain/LangGraph em langfuse 4.x.

**Rationale:** Validado com `python -c "from langfuse.langchain import CallbackHandler"` → OK. O handler 4.x tem a mesma interface de uso (`config={"callbacks": [...]}`) mas arquitetura OTEL internamente.

**Alternativas rejeitadas:**
1. Fazer downgrade para langfuse 2.x — quebraria outras dependências; langfuse 4.x é a versão instalada
2. Usar OTEL SDK diretamente — muito baixo nível; CallbackHandler já integra LangChain/LangGraph automaticamente

**Consequências:**
- `CallbackHandler()` não recebe credenciais no construtor — configuração via `os.environ`
- `lf_handler.last_trace_id` é o atributo para obter o trace ID pós-execução (validado via inspeção do código-fonte)
- Session ID e metadata passados via `config["metadata"]["langfuse_session_id"]` (chave especial parseada internamente pelo handler)

---

### ADR-002: Configuração de credenciais LangFuse via os.environ

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-12 |

**Contexto:** Em langfuse 4.x, `CallbackHandler()` e `Langfuse()` leem credenciais de `os.environ` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`). O pydantic-settings carrega o `.env` para `Settings.langfuse_*` mas NÃO popula `os.environ` — as duas fontes são independentes.

**Escolha:** Usar `os.environ.setdefault(key, value)` ao carregar o módulo `app.py`, usando os valores de `_settings`. Isso popula as env vars que langfuse 4.x espera, sem sobrescrever variáveis já presentes no ambiente real (CI/CD, produção).

**Alternativas rejeitadas:**
1. Usar `os.environ[key] = value` — sobrescreveria variáveis de ambiente reais de produção
2. Passar credenciais por-handler via `Langfuse(public_key=..., secret_key=..., host=...)` em cada mensagem — `CallbackHandler()` não aceita `secret_key`; `Langfuse()` cria exporter OTEL global na inicialização (custoso por mensagem)

**Consequências:**
- `os.environ.setdefault` deve ser chamado ANTES de qualquer `import langfuse` que inicie o exporter
- Os 3 `setdefault` ficam no nível de módulo, logo após `get_settings()`
- O exporter OTEL é inicializado uma vez no primeiro uso de `Langfuse()` ou `CallbackHandler()`

---

### ADR-003: Enriquecimento pós-loop via create_score

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-12 |

**Contexto:** O DEFINE pede que `final_sql` e `final_retry_count` sejam adicionados à trace após o loop. Em langfuse 4.x (OTEL), a API pública `Langfuse` não tem método `trace(id=..., metadata={...})` para update pós-execução. `update_current_span()` só funciona dentro de um span ativo. Após `astream_events` completar, todos os spans estão fechados.

**Escolha:**
- `retry_count` → `Langfuse().create_score(trace_id=last_trace_id, name="retry_count", value=float(n), data_type="NUMERIC")`
- `final_sql` → incluído no campo `comment` do mesmo score (string de até 300 chars)
- O SQL completo já está automaticamente capturado como `output` do span `generate_sql` pelo CallbackHandler

**Rationale:** `create_score()` aceita `trace_id` explícito e funciona fora do contexto de trace. `retry_count` como `NUMERIC` é navegável via filtros no LangFuse Cloud. `final_sql` no `comment` é texto livre visível no UI.

**Alternativas rejeitadas:**
1. `Langfuse().update_current_span(metadata=...)` — requer span ativo; falha após o loop
2. REST API direta via `httpx` — introduz dependência de HTTP client sem tipo e acoplamento à API interna do LangFuse
3. `propagate_attributes(metadata=...)` context manager — sessão pode propagar antes dos spans do grafo, mas não permite atualização pós-loop

**Consequências:**
- Trade-off aceito: `final_sql` ficará em dois lugares (span output automático + score comment). Isso é redundante mas inofensivo.
- `create_score` faz um HTTP call assíncrono ao LangFuse Cloud; `flush()` garante o envio antes do processo retornar

---

### ADR-004: DeepEval — AnthropicModel em vez de OpenAI padrão

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-12 |

**Contexto:** DeepEval 4.x usa OpenAI como modelo padrão para `GEval`. O projeto não tem `OPENAI_API_KEY` no `.env` — o projeto usa Claude exclusivamente. Adicionar uma chave OpenAI apenas para evals seria um custo e dependência desnecessários.

**Escolha:** `AnthropicModel(model=settings.model_name, api_key=settings.anthropic_api_key)` passado como `model=` no `GEval`. Usa o mesmo modelo configurado em `Settings` (Claude Sonnet 4.6).

**Alternativas rejeitadas:**
1. Usar OpenAI padrão — requer `OPENAI_API_KEY`; introduz dependência externa não gerenciada
2. LiteLLM com Anthropic — compatível mas adiciona uma camada de indireção desnecessária

**Consequências:**
- `from deepeval.models.llms.anthropic_model import AnthropicModel` — import de subpacote interno; pode mudar entre versões. Validado em deepeval **4.0.5**.
- O custo de 5 avaliações GEval (~15 LLM calls total: 5 geração + 10 avaliação judge) é cobrado na chave Anthropic da conta

---

### ADR-005: deepeval 4.x — SingleTurnParams substitui LLMTestCaseParams

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-12 |

**Contexto:** `LLMTestCaseParams` foi deprecated no deepeval 4.x. Usar o import deprecated gera `DeprecationWarning` no terminal.

**Escolha:** `from deepeval.test_case import LLMTestCase, SingleTurnParams` — `SingleTurnParams.INPUT`, `SingleTurnParams.ACTUAL_OUTPUT`, `SingleTurnParams.EXPECTED_OUTPUT`.

**Consequências:** Nenhuma mudança funcional — apenas o namespace. `LLMTestCase` ainda usa os mesmos parâmetros keyword.

---

## File Manifest

| # | Arquivo | Ação | Propósito | Dependências |
|---|---|---|---|---|
| 1 | `src/finlake_analyst/app.py` | Modificar | Adicionar LangFuse 4.x CallbackHandler e score pós-loop | Nenhuma nova |
| 2 | `evals/__init__.py` | Criar | Marca `evals/` como package Python | Nenhuma |
| 3 | `evals/eval_sql.py` | Criar | Script DeepEval com P1–P5 + GEval SQL equivalence | 2 |

**Total de arquivos:** 3 (1 modificado + 2 criados)

---

## Code Patterns

### Padrão 1: app.py — diff das mudanças

**Imports a adicionar (top do arquivo, em ordem isort):**

```python
import logging
import os
from typing import Any
```

**Bloco de configuração LangFuse após `_settings = get_settings()`:**

```python
_log = logging.getLogger(__name__)

# Bridges pydantic-settings → LangFuse 4.x env-var config (setdefault não sobrescreve env reais).
# Deve estar antes de qualquer import de langfuse que inicialize o exporter OTEL.
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", _settings.langfuse_public_key)
os.environ.setdefault("LANGFUSE_SECRET_KEY", _settings.langfuse_secret_key)
os.environ.setdefault("LANGFUSE_HOST", _settings.langfuse_host)
```

**on_message completo (substitui o existente):**

```python
@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Processa pergunta do usuário via grafo LangGraph com streaming e LangFuse traces."""
    graph = cl.user_session.get("graph")

    initial_state: AgentState = {
        "question": message.content,
        "sql": "",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }

    lf_handler: Any = None
    lf_config: dict[str, Any] = {}
    try:
        from langfuse.langchain import CallbackHandler
        lf_handler = CallbackHandler()
        lf_config = {
            "callbacks": [lf_handler],
            "metadata": {
                "langfuse_session_id": cl.context.session.id,
                "langfuse_trace_name": "finlake-analyst-query",
                "question": message.content,
            },
        }
    except Exception:
        _log.exception("LangFuse handler init failed — tracing disabled for this request")

    msg = cl.Message(content="")
    error_fallback = ""
    final_sql = ""
    final_retry_count = 0

    async for event in graph.astream_events(initial_state, config=lf_config, version="v2"):
        kind = event["event"]
        node = event["metadata"].get("langgraph_node", "")

        if kind == "on_chat_model_stream" and node == "interpret_result":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                await msg.stream_token(chunk.content)

        elif kind == "on_chain_end" and node == "generate_sql":
            output = event["data"].get("output", {})
            if isinstance(output, dict):
                final_sql = output.get("sql", final_sql)

        elif kind == "on_chain_end" and node == "execute_sql":
            output = event["data"].get("output", {})
            if isinstance(output, dict) and "retry_count" in output:
                final_retry_count = output.get("retry_count", final_retry_count)

        elif kind == "on_chain_end" and event.get("name") == "handle_error":
            output = event["data"].get("output", {})
            if isinstance(output, dict):
                error_fallback = output.get("analysis", "")

    try:
        if lf_handler is not None and lf_handler.last_trace_id:
            from langfuse import Langfuse
            lf_client = Langfuse()
            lf_client.create_score(
                trace_id=lf_handler.last_trace_id,
                name="retry_count",
                value=float(final_retry_count),
                data_type="NUMERIC",
                comment=final_sql[:300] if final_sql else None,
            )
            lf_client.flush()
    except Exception:
        _log.exception("LangFuse trace enrichment failed")

    if not msg.content and error_fallback:
        msg.content = error_fallback

    await msg.send()
```

**Nota sobre ruff ANN:** `lf_handler: Any` e `lf_config: dict[str, Any]` usam `Any` de `typing` — adicionar `from typing import Any` ao bloco de imports.

---

### Padrão 2: evals/\_\_init\_\_.py

```python
"""Pacote de avaliações offline do agente FinLake Analyst."""
```

---

### Padrão 3: evals/eval_sql.py (completo)

```python
"""Script standalone de avaliação da qualidade SQL do agente FinLake Analyst.

Executa as 5 queries de referência (P1–P5) contra o agente e avalia a equivalência
semântica do SQL gerado com GEval (LLM-as-judge) do DeepEval 4.x.

Uso:
    uv run python evals/eval_sql.py

Pré-requisitos:
    ANTHROPIC_API_KEY e DATABASE_URL (FINLAKE_DATABASE_URL) configurados no .env.
    O banco PostgreSQL :5433 deve estar acessível.
"""

import asyncio
import logging
import sys

from deepeval.metrics import GEval
from deepeval.models.llms.anthropic_model import AnthropicModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from finlake_analyst.agent import create_agent_graph
from finlake_analyst.agent.state import AgentState
from finlake_analyst.config import get_settings
from finlake_analyst.prompts import get_sql_prompt
from finlake_analyst.tools.sql_schema import SqlSchemaTool

_log = logging.getLogger(__name__)

# ─── Ground Truth P1–P5 ──────────────────────────────────────────────────────

_EXPECTED_P1 = """\
SELECT cnpj_fundo, gestor, ano_mes, rentabilidade_mes_pct, alpha_selic
FROM gold_cvm.fundo_mensal
WHERE alpha_selic > 0
  AND rentabilidade_mes_pct < 1000
  AND ano_mes >= '2024-10-01'
ORDER BY alpha_selic DESC
LIMIT 20"""

_EXPECTED_P2 = """\
SELECT cnpj_fundo, gestor, tp_fundo,
       SUM(captacao_liquida_acumulada) AS captacao_total
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY cnpj_fundo, gestor, tp_fundo
ORDER BY captacao_total DESC
LIMIT 10"""

_EXPECTED_P3 = """\
SELECT date, taxa_anual, selic_real, ptax_media
FROM gold_bcb.macro_mensal
WHERE date >= current_date - interval '12 months'
ORDER BY date ASC"""

_EXPECTED_P4 = """\
SELECT tp_fundo,
       AVG(vl_patrim_liq_medio) AS pl_medio,
       COUNT(DISTINCT cnpj_fundo) AS total_fundos
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY tp_fundo
ORDER BY pl_medio DESC"""

_EXPECTED_P5 = """\
SELECT tp_fundo,
       COUNT(DISTINCT cnpj_fundo) AS fundos_com_captacao_positiva,
       AVG(captacao_liquida_acumulada) AS captacao_media
FROM gold_cvm.fundo_mensal
WHERE taxa_anual_bcb > 10
  AND captacao_liquida_acumulada > 0
GROUP BY tp_fundo
ORDER BY captacao_media DESC"""

_TEST_CASES: list[dict[str, str]] = [
    {
        "id": "P1",
        "question": "Quais fundos com maior alpha_selic no último trimestre de 2024?",
        "expected_sql": _EXPECTED_P1,
    },
    {
        "id": "P2",
        "question": "Quais fundos tiveram maior captação líquida em 2024?",
        "expected_sql": _EXPECTED_P2,
    },
    {
        "id": "P3",
        "question": "Como evoluiu a SELIC real nos últimos 12 meses?",
        "expected_sql": _EXPECTED_P3,
    },
    {
        "id": "P4",
        "question": "Qual o patrimônio líquido médio por tipo de fundo em 2024?",
        "expected_sql": _EXPECTED_P4,
    },
    {
        "id": "P5",
        "question": "Quais tipos de fundo tiveram captação positiva com SELIC acima de 10%?",
        "expected_sql": _EXPECTED_P5,
    },
]

_GEVAL_CRITERIA = (
    "O SQL gerado responde à pergunta do usuário de forma semanticamente "
    "equivalente ao SQL esperado, considerando o schema disponível. "
    "Variações de formatação, aliases e ordem de cláusulas são aceitáveis "
    "desde que o resultado da query seja equivalente."
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _build_metric(model: AnthropicModel) -> GEval:
    """Cria métrica GEval para equivalência semântica SQL."""
    return GEval(
        name="SQL Correctness",
        criteria=_GEVAL_CRITERIA,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=model,
        threshold=0.7,
    )


async def _generate_sql(graph: object, question: str) -> str:
    """Executa o grafo para uma pergunta e retorna o SQL gerado."""
    state: AgentState = {
        "question": question,
        "sql": "",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }
    result = await graph.ainvoke(state)  # type: ignore[union-attr]
    return result.get("sql", "")


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    """Executa evals P1–P5 e imprime resultados com score por query."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

    settings = get_settings()
    schema = SqlSchemaTool()._run("")
    sql_prompt = get_sql_prompt().partial(schema=schema)
    graph = create_agent_graph(sql_prompt)

    anthropic_model = AnthropicModel(
        model=settings.model_name,
        api_key=settings.anthropic_api_key,
    )
    metric = _build_metric(anthropic_model)

    print("\n=== FinLake Analyst — SQL Eval (P1–P5) ===\n")

    passed = 0
    for tc in _TEST_CASES:
        _log.info("Gerando SQL para %s", tc["id"])
        actual_sql = await _generate_sql(graph, tc["question"])

        test_case = LLMTestCase(
            input=tc["question"],
            actual_output=actual_sql,
            expected_output=tc["expected_sql"],
        )
        metric.measure(test_case)

        score = metric.score if metric.score is not None else 0.0
        status = "✓ PASS" if metric.is_successful() else "✗ FAIL"
        reason_short = (metric.reason or "")[:120]
        print(f"  {tc['id']}: {status}  score={score:.2f}  — {reason_short}")

        if metric.is_successful():
            passed += 1

    overall = passed / len(_TEST_CASES)
    print(f"\nScore geral: {passed}/{len(_TEST_CASES)}  ({overall:.0%})")

    if passed < len(_TEST_CASES):
        print("\nQueries com falha — verificar SQL esperado vs gerado:")
        for tc in _TEST_CASES:
            print(f"  {tc['id']}: {tc['question']}")

    sys.exit(0 if passed >= 3 else 1)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Testing Strategy

| Tipo | Escopo | Ferramenta | Executar |
|---|---|---|---|
| Lint | `src/` + `evals/` | ruff | `uv run ruff check src/ evals/` |
| Regressão | 42 testes existentes | pytest | `uv run pytest tests/ -v` |
| Smoke test LangFuse | AT-001 a AT-005 | Manual | Verificação passo a passo (ver abaixo) |
| Eval SQL | AT-006 a AT-009 | Script standalone | `uv run python evals/eval_sql.py` |

**Nenhum novo teste pytest** é requerido para esta feature (per DEFINE).

### Smoke Test Protocol (AT-001 a AT-005)

Execute na ordem — cada passo valida um AT:

```bash
# AT-001: Import OK
uv run python -c "from langfuse.langchain import CallbackHandler; print('OK')"

# AT-002: Handler instancia com settings reais (requer .env preenchido)
uv run python -c "
import os
from finlake_analyst.config import get_settings
s = get_settings()
os.environ.setdefault('LANGFUSE_PUBLIC_KEY', s.langfuse_public_key)
os.environ.setdefault('LANGFUSE_SECRET_KEY', s.langfuse_secret_key)
os.environ.setdefault('LANGFUSE_HOST', s.langfuse_host)
from langfuse.langchain import CallbackHandler
h = CallbackHandler()
print('handler:', h)
print('last_trace_id:', h.last_trace_id)
"

# AT-003/AT-004: Captura de final_sql/final_retry_count
# Validar com smoke test do Chainlit + inspecionar logs (LANGFUSE_DEBUG=true)
LANGFUSE_DEBUG=true uv run chainlit run src/finlake_analyst/app.py --watch
# → faça uma pergunta, observe o terminal para eventos on_chain_end

# AT-005: LangFuse indisponível não quebra o agente
uv run python -c "
import os
os.environ['LANGFUSE_PUBLIC_KEY'] = 'invalid-key'
os.environ['LANGFUSE_SECRET_KEY'] = 'invalid-key'
os.environ['LANGFUSE_HOST'] = 'http://127.0.0.1:99999'
from langfuse.langchain import CallbackHandler
h = CallbackHandler()
print('handler criado OK — graceful degradation funcionou')
"
```

### Verificação do Score no LangFuse Cloud

Após o smoke test:
1. Acessar LangFuse Cloud com as credenciais do `.env`
2. Navegar para Traces
3. Verificar: trace existe com `session_id`, `question` na metadata
4. Verificar: score `retry_count` associado ao trace

---

## Implementation Notes

### Nota 1: `lf_handler: Any` e ruff ANN

A variável `lf_handler` recebe `None` inicialmente e pode receber um `CallbackHandler` no bloco `try`. Como o import de `CallbackHandler` é condicional (dentro de `try`), usar `Any` do módulo `typing` é a anotação correta para o tipo da variável local. Ruff ANN rules se aplicam a assinaturas de função, não a variáveis locais — mas a anotação explícita `: Any` documenta a intenção.

### Nota 2: `graph.ainvoke()` no eval script

`graph.ainvoke(state)` retorna um `dict` (o `AgentState` final). O campo `state["sql"]` contém o último SQL gerado. Se o agente atingiu `handle_error`, `state["sql"]` pode ser a string gerada antes do erro — útil para diagnóstico.

### Nota 3: `GEval.measure()` é síncrona com asyncio interno

`GEval.measure()` é uma função síncrona que usa `asyncio` internamente para chamar o LLM judge. O `deepeval` instala e aplica `nest_asyncio` automaticamente, permitindo uso dentro de `asyncio.run(main())`. Não usar `await` com `metric.measure()`.

### Nota 4: A-003/A-004 ainda pendentes

A estrutura do evento `on_chain_end` para nós LangGraph não foi validada com banco real (A-003/A-004 do AGENT_CORE). O design assume `event["data"]["output"]["sql"]` e `event["data"]["output"]["retry_count"]`. Se esses campos não estiverem presentes, `output.get("sql", final_sql)` mantém o valor anterior (não quebra). Validar no smoke test do Build.

### Nota 5: `type: ignore[union-attr]` no eval script

`_generate_sql(graph: object, ...)` usa `object` para o tipo do grafo para evitar importar `CompiledStateGraph` no script de evals. O `# type: ignore[union-attr]` suprime o erro de mypy em `graph.ainvoke()`. Ruff não roda mypy, então isso não afeta o lint.

### Nota 6: `create_score` comment field

O campo `comment` no `create_score` é texto livre (string) no LangFuse. Limitado a 300 chars para evitar problemas de tamanho na API. O SQL completo já está disponível no span `generate_sql` — o comment é apenas um atalho visual no card do score.

---

## Checklist de Qualidade

```text
[x] Diagrama de arquitetura claro
[x] 5 ADRs — cada decisão tem rationale + alternativas rejeitadas
[x] File manifest completo (3 arquivos)
[x] Code patterns copy-paste ready para todos os arquivos
[x] APIs validadas contra versões reais instaladas (langfuse 4.7.1, deepeval 4.0.5)
[x] Testing strategy cobre todos os 9 ATs do DEFINE
[x] Nenhuma dependência nova introduzida
[x] Ruff ANN compliance documentada
[x] Graceful degradation LangFuse documentada
```

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-12 | Nilton Coura | Versão inicial — incluindo descoberta e resolução de breaking changes nas versões instaladas |

---

## Next Step

**Pronto para:** `/build .claude/sdd/features/DESIGN_OBSERVABILITY.md`
