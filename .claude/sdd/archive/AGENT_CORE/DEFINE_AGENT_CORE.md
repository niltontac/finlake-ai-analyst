# DEFINE: AGENT_CORE

> `StateGraph` LangGraph que orquestra SQL_TOOL + PROMPTS + Claude para responder perguntas financeiras em português via Chainlit.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | AGENT_CORE |
| **Data** | 2026-06-11 |
| **Autor** | Nilton Coura |
| **Status** | ✅ Shipped |
| **Clarity Score** | 14/15 |

---

## Problem Statement

O projeto tem todos os blocos funcionais — `SqlExecuteTool`, `SqlSchemaTool`, `get_sql_prompt()`, `get_interpretation_prompt()` — mas nenhum orquestrador que os conecta. O `app.py` Chainlit é um placeholder que não responde perguntas reais. Sem o AGENT_CORE, o usuário digita uma pergunta financeira e recebe apenas "O agente está em construção". A feature entrega o grafo que fecha esse gap: pergunta em → análise financeira em português out.

---

## Target Users

| Usuário | Papel | Pain Point |
|---|---|---|
| Nilton Coura | Desenvolvedor / dono do projeto | Precisa do grafo testável e integrável ao Chainlit para demonstrar o agente funcionando end-to-end |
| Usuário final Chainlit | Analista ou investidor brasileiro | Faz perguntas sobre fundos e SELIC e espera receber análise financeira contextualizada, não SQL bruto |

---

## Goals

| Prioridade | Goal |
|---|---|
| **MUST** | Criar `agent/state.py` com `AgentState(TypedDict)` — 6 campos: `question`, `sql`, `sql_result`, `retry_count`, `error`, `analysis` |
| **MUST** | Criar `agent/nodes.py` com 4 funções async: `generate_sql`, `execute_sql`, `interpret_result`, `handle_error` |
| **MUST** | Criar `agent/graph.py` com `StateGraph`, edges condicionais de retry, e `create_agent_graph(sql_prompt) -> CompiledStateGraph` |
| **MUST** | Exportar `create_agent_graph` via `agent/__init__.py` |
| **MUST** | Atualizar `app.py`: `on_chat_start` injeta schema no sql_prompt e armazena grafo na sessão; `on_message` executa com streaming |
| **MUST** | Filtrar streaming por `langgraph_node == "interpret_result"` — SQL nunca exibido ao usuário |
| **MUST** | `handle_error` retorna mensagem em português quando `retry_count >= 2` (sem expor `SQL_ERROR:` ou stack trace) |
| **MUST** | `generate_sql` inclui o erro anterior no contexto da pergunta quando `retry_count > 0` |
| **SHOULD** | Testes unitários dos nós com mock do LLM e das tools |

---

## Success Criteria

- [ ] `create_agent_graph(sql_prompt)` retorna `CompiledStateGraph` sem erro
- [ ] Pergunta simples (ex: "Qual a SELIC atual?") resulta em `analysis` não-vazia sem levantar exceção
- [ ] Quando `SqlExecuteTool` retorna `SQL_ERROR:` e `retry_count < 2`, o grafo redireciona para `generate_sql` com o erro no contexto
- [ ] Quando `retry_count >= 2` e ainda há `SQL_ERROR:`, `handle_error` é invocado e retorna mensagem em português
- [ ] Tokens do nó `interpret_result` chegam ao usuário via streaming; tokens de `generate_sql` não aparecem
- [ ] `ruff check src/` zero violations nos arquivos novos
- [ ] `pytest tests/test_agent_*.py` passa sem conexão ao banco ou API real

---

## Acceptance Tests

| ID | Cenário | Given | When | Then |
|---|---|---|---|---|
| AT-001 | Grafo compila sem erro | `sql_prompt` mockado | `create_agent_graph(sql_prompt)` | Retorna `CompiledStateGraph`, sem exceção |
| AT-002 | `generate_sql` retorna SQL no state | LLM mock retorna `"SELECT 1"` | `generate_sql(state, ...)` | `state["sql"] == "SELECT 1"` |
| AT-003 | `generate_sql` em retry inclui erro no contexto | `state["retry_count"] = 1`, `state["error"] = "column x"` | LLM mock captura mensagem | Mensagem contém `"column x"` (erro anterior) |
| AT-004 | `execute_sql` chama a tool com o SQL do state | `state["sql"] = "SELECT 1"`, tool mockada | `execute_sql(state, ...)` | Tool chamada com `"SELECT 1"` |
| AT-005 | Edge condicional — retry quando SQL_ERROR | `sql_result = "SQL_ERROR: coluna inválida"`, `retry_count = 0` | Edge condicional avaliada | Próximo nó é `generate_sql` |
| AT-006 | Edge condicional — handle_error quando retry esgotado | `sql_result = "SQL_ERROR: ..."`, `retry_count = 2` | Edge condicional avaliada | Próximo nó é `handle_error` |
| AT-007 | `handle_error` não expõe SQL_ERROR ao usuário | `state["error"] = "SQL_ERROR: syntax error"` | `handle_error(state)` | `state["analysis"]` não contém `"SQL_ERROR"` |
| AT-008 | `handle_error` responde em português | Qualquer estado de erro | `handle_error(state)` | `state["analysis"]` contém texto em português |
| AT-009 | `interpret_result` retorna análise no state | LLM mock retorna `"Análise: SELIC em 10.75%"` | `interpret_result(state, ...)` | `state["analysis"] == "Análise: SELIC em 10.75%"` |

---

## Out of Scope

- LangFuse callbacks e traces — feature OBSERVABILITY; não bloqueia o agente funcionar
- Memória de conversa (histórico de mensagens entre perguntas) — v1 stateless; cada pergunta é independente
- Nó de clarificação de ambiguidade ("qual período você quer?") — AGENT_CORE decide com o que tem
- Autenticação Chainlit — já configurada via `CHAINLIT_AUTH_SECRET` no `.env`
- Nó de validação SQL LLM-based (`sql_db_query_checker`) — rejeitado no SQL_TOOL brainstorm
- DeepEval integrado ao grafo — avaliação offline, não inline
- Indicador de loading ("pensando...") durante SQL generation — nice-to-have, não bloqueia MVP

---

## Constraints

| Tipo | Constraint | Impacto |
|---|---|---|
| Técnico | Python 3.12, type hints obrigatórios, docstrings públicas | Todos os arquivos novos seguem convenções finlake-brasil |
| Técnico | `langgraph>=0.2` e `langchain-anthropic>=0.3` já em `pyproject.toml` | Usar `StateGraph` de `langgraph` e `ChatAnthropic` de `langchain_anthropic` |
| Técnico | `src/` layout | Novos arquivos em `src/finlake_analyst/agent/` |
| Técnico | Testes sem conexão real ao banco ou API | Mocks via `unittest.mock.patch` ou injeção de dependência |
| UX | SQL gerado nunca exibido ao usuário | Filtrar `langgraph_node == "interpret_result"` no streaming |
| Comportamento | Máximo 2 retries em `SQL_ERROR:` | `retry_count` incrementado em `execute_sql`; edge para `handle_error` quando `>= 2` |

---

## Technical Context

| Aspecto | Valor | Notas |
|---|---|---|
| **Deployment Location** | `src/finlake_analyst/agent/` + `src/finlake_analyst/app.py` | `state.py`, `nodes.py`, `graph.py`, `__init__.py`; `app.py` modificado |
| **KB Domains** | `ai-data-engineering/llmops-patterns`, `python/clean-architecture` | Padrões LangGraph StateGraph e arquitetura limpa |
| **IaC Impact** | None | Sem nova infraestrutura; LLM via API Anthropic já configurada |

---

## Interface do Grafo

### `create_agent_graph(sql_prompt: ChatPromptTemplate) -> CompiledStateGraph`

```python
# Parâmetro: sql_prompt já com {schema} pré-vinculado via .partial()
# Retorno: grafo compilado pronto para .astream_events()
#
# Fluxo interno:
#   START → generate_sql → execute_sql → (condicional)
#     ├─ SQL_ERROR + retry_count < 2 → generate_sql (com erro no contexto)
#     ├─ SQL_ERROR + retry_count >= 2 → handle_error → END
#     └─ sucesso → interpret_result → END
```

### `AgentState (TypedDict)`

```python
class AgentState(TypedDict):
    question: str       # pergunta original do usuário
    sql: str            # SQL gerado (última versão)
    sql_result: str     # resultado do SqlExecuteTool ou "SQL_ERROR:..."
    retry_count: int    # tentativas falhadas (0 = primeira tentativa, max 2)
    error: str | None   # último erro para contexto no retry
    analysis: str       # análise financeira final (output de interpret_result)
```

### Integração `app.py`

```python
# on_chat_start — uma vez por sessão
schema = SqlSchemaTool()._run("")
sql_prompt = get_sql_prompt().partial(schema=schema)
graph = create_agent_graph(sql_prompt)
cl.user_session.set("graph", graph)

# on_message — por pergunta
graph = cl.user_session.get("graph")
msg = cl.Message(content="")
async for event in graph.astream_events(initial_state, version="v2"):
    if (event["event"] == "on_chat_model_stream"
            and event["metadata"].get("langgraph_node") == "interpret_result"):
        await msg.stream_token(event["data"]["chunk"].content)
await msg.send()
```

---

## Assumptions

| ID | Suposição | Se Errada, Impacto | Validado? |
|---|---|---|---|
| A-001 | `ChatAnthropic.ainvoke()` dentro de um nó LangGraph emite `on_chat_model_stream` events via `astream_events(version="v2")` | Streaming não funcionaria; precisaria de abordagem diferente | [ ] Validar no Build |
| A-002 | `event["metadata"]["langgraph_node"]` está disponível em eventos `on_chat_model_stream` com `version="v2"` | Filtro de streaming falharia silenciosamente (exporia SQL ao usuário) | [ ] Validar no Build |
| A-003 | `cl.user_session.set/get` funciona corretamente para armazenar o grafo compilado entre `on_chat_start` e `on_message` | Grafo seria recriado a cada mensagem (degradação de performance, mas não falha) | [x] Padrão documentado Chainlit |

---

## Clarity Score Breakdown

| Elemento | Score (0-3) | Notas |
|---|---|---|
| Problem | 3 | Específico: blocos prontos, orquestrador faltando, usuário recebe placeholder |
| Users | 2 | Nilton (dev) + usuário final Chainlit — segundo persona genérico |
| Goals | 3 | 9 goals MoSCoW, interface de todos os artefatos especificada |
| Success | 3 | 7 critérios testáveis: grafo compila, retry funciona, streaming filtra, português no erro |
| Scope | 3 | 7 itens fora de escopo explícitos + constraints de comportamento documentados |
| **Total** | **14/15** | Passa o gate (12/15) |

---

## Open Questions

- **A-001/A-002**: Validar no início do Build que `astream_events(version="v2")` com `ChatAnthropic` emite `on_chat_model_stream` com `langgraph_node` no metadata. Se não funcionar, abordagem alternativa: usar `on_llm_new_token` ou filtrar por tag do nó.

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-11 | Nilton Coura | Versão inicial gerada a partir de BRAINSTORM_AGENT_CORE.md |
| 1.1 | 2026-06-12 | ship-agent | Shipped and archived |

---

## Next Step

**Pronto para:** `/design .claude/sdd/features/DEFINE_AGENT_CORE.md`
