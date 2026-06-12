# BUILD REPORT: AGENT_CORE

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | AGENT_CORE |
| **Build Date** | 2026-06-12 |
| **Status** | ✅ Completo |
| **Tests** | 42/42 passed (20 novos) |
| **Lint** | `ruff check src/ tests/` — All checks passed! |

---

## Summary

O AGENT_CORE conecta todos os blocos já entregues (SQL_TOOL, PROMPTS, Claude) em um `StateGraph` LangGraph stateful. O `app.py` Chainlit foi atualizado do placeholder para a implementação real — o agente agora responde perguntas financeiras em português com streaming.

---

## Tasks Completed

| # | Arquivo | Ação | Status |
|---|---|---|---|
| 1 | `src/finlake_analyst/agent/state.py` | Criar | ✅ |
| 2 | `src/finlake_analyst/agent/nodes.py` | Criar | ✅ |
| 3 | `src/finlake_analyst/agent/graph.py` | Criar | ✅ |
| 4 | `src/finlake_analyst/agent/__init__.py` | Modificar | ✅ |
| 5 | `src/finlake_analyst/app.py` | Modificar | ✅ |
| 6 | `tests/test_agent_nodes.py` | Criar | ✅ |
| 7 | `tests/test_agent_graph.py` | Criar | ✅ |

---

## Test Results

```
42 passed, 1 warning in 0.46s
```

| Módulo | Novos Testes | Resultado |
|---|---|---|
| `test_agent_nodes.py` | 13 | ✅ 13/13 |
| `test_agent_graph.py` | 7 | ✅ 7/7 |
| `test_config.py` | — | ✅ 3/3 (regressão) |
| `test_prompts.py` | — | ✅ 8/8 (regressão) |
| `test_sql_execute.py` | — | ✅ 8/8 (regressão) |
| `test_sql_schema.py` | — | ✅ 3/3 (regressão) |

**Warning pré-existente:** `DeprecationWarning` em `langchain-community` (originado no SQL_TOOL, não é novo).

---

## Acceptance Tests Verification

| ID | Cenário | Status |
|---|---|---|
| AT-001 | `create_agent_graph()` retorna grafo compilado sem exceção | ✅ `test_create_agent_graph_compiles` |
| AT-002 | `generate_sql` retorna SQL no state | ✅ `test_generate_sql_returns_sql_in_state` |
| AT-003 | `generate_sql` em retry inclui erro no contexto | ✅ `test_generate_sql_retry_includes_error_context` |
| AT-004 | `execute_sql` chama a tool com o SQL do state | ✅ `test_execute_sql_calls_tool_with_state_sql` |
| AT-005 | Edge condicional — retry quando SQL_ERROR + retry_count < 2 | ✅ `test_route_sql_error_with_retry_available_goes_to_generate_sql` |
| AT-006 | Edge condicional — handle_error quando retry_count >= 2 | ✅ `test_route_sql_error_retry_count_2_goes_to_handle_error` |
| AT-007 | `handle_error` não expõe SQL_ERROR ao usuário | ✅ `test_handle_error_does_not_expose_sql_error` |
| AT-008 | `handle_error` responde em português | ✅ `test_handle_error_returns_portuguese_text` |
| AT-009 | `interpret_result` retorna análise no state | ✅ `test_interpret_result_returns_analysis` |

---

## Files Created / Modified

### Novos arquivos

**`src/finlake_analyst/agent/state.py`** (12 linhas)
- `AgentState` TypedDict com 6 campos: `question`, `sql`, `sql_result`, `retry_count`, `error`, `analysis`

**`src/finlake_analyst/agent/nodes.py`** (78 linhas)
- `make_generate_sql_node(llm, sql_prompt)` → closure `generate_sql`
  - Injeta contexto de erro na pergunta quando `retry_count > 0`
  - Chama `llm.ainvoke()` e retorna `{"sql": response.content.strip()}`
- `make_execute_sql_node(tool)` → closure `execute_sql`
  - Chama `tool._arun(state["sql"])`
  - Incrementa `retry_count` e seta `error` quando resultado começa com `SQL_ERROR:` ou `SECURITY_ERROR:`
- `make_interpret_result_node(llm, interpretation_prompt)` → closure `interpret_result`
  - Chama `llm.ainvoke()` com `question`, `sql`, `result` do state
- `handle_error(state)` → retorna `_HANDLE_ERROR_MSG` em português sem expor detalhes técnicos

**`src/finlake_analyst/agent/graph.py`** (68 linhas)
- `_route_after_execute(state)` → função de routing pura (testável sem LangGraph)
  - `SQL_ERROR:/SECURITY_ERROR:` + `retry_count < 2` → `"generate_sql"`
  - `SQL_ERROR:/SECURITY_ERROR:` + `retry_count >= 2` → `"handle_error"`
  - sucesso → `"interpret_result"`
- `create_agent_graph(sql_prompt)` → instancia LLM, tools, monta `StateGraph`, compila

**`tests/test_agent_nodes.py`** (130 linhas, 13 testes)

**`tests/test_agent_graph.py`** (68 linhas, 7 testes)

### Arquivos modificados

**`src/finlake_analyst/agent/__init__.py`** — passou de skeleton para re-exportar `create_agent_graph`

**`src/finlake_analyst/app.py`** — substituído placeholder por implementação real:
- `on_chat_start`: `SqlSchemaTool()._run("")` → `get_sql_prompt().partial(schema=schema)` → `create_agent_graph(sql_prompt)` → `cl.user_session.set("graph", graph)`
- `on_message`: `graph.astream_events(initial_state, version="v2")` com filtro `langgraph_node == "interpret_result"` para streaming; captura `handle_error` output via `on_chain_end`

---

## Autonomous Decisions

| Decisão | Contexto | Escolha |
|---|---|---|
| `state` não-usado em `handle_error` | `handle_error(state: AgentState) -> dict` — `state` não é usado no corpo | Mantido sem `del state` (ARG não está em `ruff select`; sem warnings) |
| `api_key=settings.anthropic_api_key` sem `SecretStr` cast | Pydantic v2 coerce `str` → `SecretStr` em runtime; sem warning do ruff | Passado diretamente; sem `# type: ignore` |
| `test_route_empty_result_goes_to_interpret_result` (teste extra) | DESIGN especificou 7 testes no `test_agent_graph.py`; adicionado caso de borda "resultado vazio não é erro" | Adicionado — cobre `SqlExecuteTool` retornar "Nenhum resultado" (msg de sucesso sem prefixo de erro) |

---

## Assumptions Validated

| Assumption | Status | Observação |
|---|---|---|
| A-001: `ChatAnthropic.ainvoke()` emite `on_chat_model_stream` via `astream_events(v2)` | ⚠️ Pendente — validar com smoke test manual | Requer `.env` com credenciais reais |
| A-002: `event["metadata"]["langgraph_node"]` disponível em `on_chat_model_stream` | ⚠️ Pendente — validar com smoke test manual | Idem |
| A-003: `cl.user_session.set/get` preserva o grafo entre `on_chat_start` e `on_message` | ✅ Confirmado | Padrão documentado Chainlit, sem necessidade de smoke test |

**Nota:** A-001 e A-002 só podem ser validadas com o agente rodando contra a API real (requerem `ANTHROPIC_API_KEY` válido). O smoke script especificado no DESIGN pode ser executado com `uv run chainlit run src/finlake_analyst/app.py --watch`.

---

## Issues Found

Nenhum blocker. Zero falhas de lint, zero falhas de teste.

---

## Next Step

**Pronto para:** `/ship .claude/sdd/features/DEFINE_AGENT_CORE.md`
