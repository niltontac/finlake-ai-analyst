# BRAINSTORM: OBSERVABILITY

**Projeto:** finlake-ai-analyst  
**Data:** 2026-06-12  
**Status:** Concluído — pronto para `/define`  
**Fase:** 0 de 5 (Brainstorm)

---

## 1. Contexto

A feature **OBSERVABILITY** adiciona visibilidade e avaliação de qualidade ao agente já funcional (AGENT_CORE shipped). Dois componentes com peso igual:

- **LangFuse Cloud** — traces de produção para debugging e monitoramento. Credenciais já presentes em `Settings` (`langfuse_public_key`, `langfuse_secret_key`, `langfuse_host`). Pacote `langfuse>=2.0` já em `dependencies`.
- **DeepEval** — avaliação offline da qualidade do SQL gerado. Pacote `deepeval>=1.4` já em `dev` dependencies.

O agente atual roda sem nenhuma instrumentação — erros de SQL silenciosos, retries invisíveis, custo desconhecido por pergunta, qualidade do SQL não mensurada.

---

## 2. Decisões Tomadas

### Q1 — Foco principal
**Decisão: ambos com peso igual** — LangFuse traces + DeepEval evals na mesma feature.

### Q2 — Profundidade LangFuse
**Decisão: médio** — trace completa + pergunta/SQL como metadata explícita + retry_count.

O mínimo (só trace automática) não seria suficiente para debugar casos onde o SQL errou mas o retry foi transparente. O completo (prompt versioning, sessions) é desnecessário em v1.

### Q3 — Métricas DeepEval
**Decisão: foco no SQL gerado** — comparar SQL gerado com SQL esperado das 5 queries validadas. A análise financeira final (AnswerRelevancy, Faithfulness) fica fora do escopo desta feature.

Motivo: o SQL é o passo crítico do pipeline — se o SQL estiver correto, a análise financeira tende a ser boa. Avaliar a análise requer escrever 5 "análises esperadas" que seriam subjetivas e difíceis de manter.

### Q4 — Execução dos evals
**Decisão: script standalone** — `evals/eval_sql.py`, rodado manualmente com `uv run python evals/eval_sql.py`. Sem integração com pytest (evita custo de API em cada `pytest` run).

### Q5 — Dataset DeepEval
**Decisão: recuperar do SQL_TOOL archive** — as 5 queries P1–P5 validadas manualmente contra o banco real servem como ground truth.

---

## 3. Abordagem Selecionada

### Componente 1: LangFuse — `CallbackHandler` automático ⭐

**Por que `CallbackHandler` em vez de SDK manual:**
O `CallbackHandler` do `langfuse.langchain` integra com LangChain/LangGraph via o sistema de callbacks — captura automaticamente todos os LLM calls (`generate_sql`, `interpret_result`), tokens, latência e custo por nó. Nenhuma modificação ao código dos nós é necessária.

**Mudanças em `app.py`:**
```python
from langfuse.callback import CallbackHandler

@cl.on_message
async def on_message(message: cl.Message) -> None:
    graph = cl.user_session.get("graph")
    settings = get_settings()

    lf_handler = CallbackHandler(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        session_id=cl.context.session.id,
        metadata={"question": message.content},
    )

    initial_state: AgentState = { ... }

    final_sql = ""
    final_retry_count = 0
    error_fallback = ""
    msg = cl.Message(content="")

    async for event in graph.astream_events(
        initial_state,
        config={"callbacks": [lf_handler]},
        version="v2",
    ):
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

    # Enriquecer trace com SQL final e retry_count
    lf_handler.langfuse.trace(
        id=lf_handler.trace_id,
        metadata={
            "question": message.content,
            "final_sql": final_sql,
            "retry_count": final_retry_count,
        },
    )
    lf_handler.langfuse.flush()

    if not msg.content and error_fallback:
        msg.content = error_fallback
    await msg.send()
```

**O que aparece no LangFuse:**
- Trace por pergunta com duração total
- Spans para `generate_sql` e `interpret_result` com input/output e tokens
- `question`, `final_sql`, `retry_count` como metadata da trace
- `session_id` agrupando traces por sessão Chainlit

**Alternativa rejeitada — SDK manual:**
Criar `langfuse.trace()` + `trace.generation()` manualmente para cada LLM call seria redundante com o que o `CallbackHandler` já faz e introduziria acoplamento desnecessário nos nós.

---

### Componente 2: DeepEval — `GEval` SQL equivalence ⭐

**Fluxo do script `evals/eval_sql.py`:**
1. Carrega `.env` via `Settings`
2. Inicializa schema via `SqlSchemaTool()._run("")`
3. Cria `sql_prompt = get_sql_prompt().partial(schema=schema)`
4. Cria `graph = create_agent_graph(sql_prompt)`
5. Para cada um dos 5 test cases:
   - Chama `graph.ainvoke(initial_state)` com a pergunta do test case
   - Extrai `final_state["sql"]` como `actual_output`
6. Avalia com `GEval` (LLM-as-judge): critério de equivalência semântica SQL
7. Imprime resultados no terminal com score por query e score geral

**Métrica GEval:**
```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

sql_correctness = GEval(
    name="SQL Correctness",
    criteria=(
        "O SQL gerado responde à pergunta do usuário de forma semanticamente "
        "equivalente ao SQL esperado, considerando o schema disponível. "
        "Variações de formatação, aliases e ordem de cláusulas são aceitáveis "
        "desde que o resultado da query seja equivalente."
    ),
    evaluation_params=[
        LLMTestCaseParams.INPUT,           # pergunta em português
        LLMTestCaseParams.ACTUAL_OUTPUT,   # SQL gerado pelo agente
        LLMTestCaseParams.EXPECTED_OUTPUT, # SQL esperado (P1–P5)
    ],
    threshold=0.7,
)
```

**Dataset — 5 test cases (P1–P5) com SQL esperado hardcoded:**

| ID | Pergunta | Tabela Principal |
|---|---|---|
| P1 | "Quais fundos com maior alpha_selic no último trimestre de 2024?" | `gold_cvm.fundo_mensal` |
| P2 | "Quais fundos tiveram maior captação líquida em 2024?" | `gold_cvm.fundo_mensal` |
| P3 | "Como evoluiu a SELIC real nos últimos 12 meses?" | `gold_bcb.macro_mensal` |
| P4 | "Qual o patrimônio líquido médio por tipo de fundo em 2024?" | `gold_cvm.fundo_mensal` |
| P5 | "Quais tipos de fundo tiveram captação positiva com SELIC acima de 10%?" | `gold_cvm.fundo_mensal` |

**SQLs esperados (do SQL_TOOL archive):**

```python
# P1
EXPECTED_SQL_P1 = """\
SELECT cnpj_fundo, gestor, ano_mes, rentabilidade_mes_pct, alpha_selic
FROM gold_cvm.fundo_mensal
WHERE alpha_selic > 0
  AND rentabilidade_mes_pct < 1000
  AND ano_mes >= '2024-10-01'
ORDER BY alpha_selic DESC
LIMIT 20"""

# P2
EXPECTED_SQL_P2 = """\
SELECT cnpj_fundo, gestor, tp_fundo,
       SUM(captacao_liquida_acumulada) AS captacao_total
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY cnpj_fundo, gestor, tp_fundo
ORDER BY captacao_total DESC
LIMIT 10"""

# P3
EXPECTED_SQL_P3 = """\
SELECT date, taxa_anual, selic_real, ptax_media
FROM gold_bcb.macro_mensal
WHERE date >= current_date - interval '12 months'
ORDER BY date ASC"""

# P4
EXPECTED_SQL_P4 = """\
SELECT tp_fundo,
       AVG(vl_patrim_liq_medio) AS pl_medio,
       COUNT(DISTINCT cnpj_fundo) AS total_fundos
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY tp_fundo
ORDER BY pl_medio DESC"""

# P5
EXPECTED_SQL_P5 = """\
SELECT tp_fundo,
       COUNT(DISTINCT cnpj_fundo) AS fundos_com_captacao_positiva,
       AVG(captacao_liquida_acumulada) AS captacao_media
FROM gold_cvm.fundo_mensal
WHERE taxa_anual_bcb > 10
  AND captacao_liquida_acumulada > 0
GROUP BY tp_fundo
ORDER BY captacao_media DESC"""
```

**Alternativa rejeitada — comparação string normalizada:**
Normalizar SQL (lowercase + strip) e comparar strings seria frágil — o Claude pode gerar SQL semanticamente idêntico com formatação diferente (ex: `BETWEEN` vs `>=/<= `, CTE vs subquery). GEval tolera variações válidas.

---

## 4. YAGNI — O que foi removido e por quê

| Removido | Motivo |
|---|---|
| LangFuse prompt versioning | Feature OBSERVABILITY não é sobre versionar prompts; AGENT_CORE já explicitou isso como escopo futuro |
| DeepEval `AnswerRelevancy` / `Faithfulness` | Usuário escolheu SQL only; métricas de análise final exigem "expected analysis" subjetiva |
| DeepEval integração pytest / CI | Custo de API por build; usuário escolheu script standalone manual |
| LangFuse custom dashboards | UI padrão do LangFuse Cloud já cobre as necessidades de v1 |
| `user_id` nos traces LangFuse | Chainlit não tem autenticação de usuário configurada; `session_id` é suficiente |
| DeepEval score target / alertas | Threshold de 0.7 no `GEval` é o padrão; sem alertas automáticos em v1 |

---

## 5. Rascunho de Requisitos para /define

### Funcionais

**LangFuse:**
- [ ] Criar `CallbackHandler` por mensagem em `on_message` com `session_id`, `question` como metadata inicial
- [ ] Passar handler via `config={"callbacks": [lf_handler]}` em `graph.astream_events`
- [ ] Capturar `final_sql` do evento `on_chain_end` do nó `generate_sql`
- [ ] Capturar `final_retry_count` do evento `on_chain_end` do nó `execute_sql`
- [ ] Após o loop: enriquecer trace com `final_sql` e `retry_count` via `lf_handler.langfuse.trace()`
- [ ] Chamar `lf_handler.langfuse.flush()` para garantir envio antes do Chainlit responder

**DeepEval:**
- [ ] Criar `evals/` como package Python (`evals/__init__.py`)
- [ ] Criar `evals/eval_sql.py` com os 5 test cases P1–P5 hardcoded
- [ ] Implementar `GEval` com critério de equivalência semântica SQL
- [ ] Script executável com `uv run python evals/eval_sql.py`
- [ ] Output no terminal: score por query (pass/fail + score numérico) + score geral

### Não-funcionais
- [ ] `CallbackHandler` não deve quebrar o agente se LangFuse estiver indisponível (try/except ou `graceful_degradation`)
- [ ] Script de evals requer `DATABASE_URL` e `ANTHROPIC_API_KEY` no `.env` — documentar no script
- [ ] `ruff check src/ evals/` zero violations
- [ ] Nenhum teste pytest novo requerido para esta feature (evals são standalone)

---

## 6. Assumptions a Validar no Build

| ID | Assumption | Como validar |
|---|---|---|
| A-001 | `lf_handler.langfuse` expõe o cliente LangFuse SDK para update pós-loop | `from langfuse.callback import CallbackHandler; h = CallbackHandler(...); print(dir(h))` |
| A-002 | `lf_handler.trace_id` ou equivalente retorna o trace ID criado automaticamente | Idem |
| A-003 | `config={"callbacks": [...]}` em `astream_events` é o mecanismo correto para passar callbacks no LangGraph 1.2.4 | Smoke test com `LANGFUSE_DEBUG=true` |
| A-004 | `event["data"]["output"]["sql"]` está disponível no `on_chain_end` do nó `generate_sql` | Já validado em A-001/A-002 do AGENT_CORE (pendente smoke test) |
| A-005 | `GEval` no DeepEval 1.4 aceita `evaluation_params` com `LLMTestCaseParams.EXPECTED_OUTPUT` | `uv run python -c "from deepeval.metrics import GEval; print('ok')"` |

---

## 7. Próximo Passo

```bash
/define .claude/sdd/features/BRAINSTORM_OBSERVABILITY.md
```
