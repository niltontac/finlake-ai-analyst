# BRAINSTORM: AGENT_CORE

**Projeto:** finlake-ai-analyst  
**Data:** 2026-06-11  
**Status:** Concluído — pronto para `/define`  
**Fase:** 0 de 5 (Brainstorm)

---

## 1. Contexto

A feature **AGENT_CORE** é o orquestrador central do FinLake Analyst — o `StateGraph` LangGraph que conecta todos os blocos já entregues:

- **SQL_TOOL**: `SqlExecuteTool` (executa SQL), `SqlSchemaTool` (retorna schema + notas de qualidade)
- **PROMPTS**: `get_sql_prompt()` (gera SQL), `get_interpretation_prompt()` (interpreta resultado financeiramente)
- **Chainlit**: interface conversacional em `app.py`
- **Anthropic Claude**: LLM configurado via `Settings.model_name`

Sem o AGENT_CORE, o projeto tem todas as peças mas nenhum "fio" que as conecta. Com ele, o usuário pode digitar "Quais fundos com maior alpha_selic em 2024?" e receber uma análise financeira em português em tempo real.

---

## 2. Decisões Tomadas

### Q1 — Estrutura do grafo
**Decisão: `StateGraph` customizado com nós explícitos**  
Motivo: o fluxo requer dois LLM calls com prompts distintos (`sql_prompt` e `interpretation_prompt`) mais um ciclo de retry controlado. O `create_react_agent` built-in do LangGraph usa um único modelo+prompt para tudo — misturaria as responsabilidades dos dois prompts. Nós explícitos também aparecem como steps separados nos traces do LangFuse (feature OBSERVABILITY).

### Q2 — Retry de SQL
**Decisão: máximo 2 retries; resposta explicativa em português quando esgotado**  
Motivo: o contexto do erro PostgreSQL (`SQL_ERROR: column "x" does not exist`) é informação suficiente para o Claude corrigir na maioria dos casos. 2 retries equilibra correção e custo de tokens. No limite, o agente responde ao usuário em português explicando o que não conseguiu consultar — sem expor stack trace.

### Q3 — Resposta ao usuário
**Decisão: streaming via `.astream_events()` + `cl.stream_token()`**  
Motivo: padrão de mercado para agentes conversacionais. A latência total não muda, mas a experiência percebida é significativamente melhor. O SQL generation ocorre silenciosamente — apenas tokens do nó `interpret_result` são streamados.

**Regra crítica de UX:** filtrar `event["metadata"]["langgraph_node"] == "interpret_result"` antes de chamar `stream_token()` — o SQL gerado é detalhe interno e nunca deve ser exibido ao usuário.

### Q4 — Grounding
**Decisão: usar as 5 queries validadas do SQL_TOOL como referência de comportamento esperado**  
As queries P1–P5 representam os padrões de consulta que o agente deve suportar corretamente.

---

## 3. Abordagem Selecionada

### Abordagem A: Módulo `agent/` com separação state / nodes / graph ⭐ Selecionada

**Organização dos arquivos:**
```
src/finlake_analyst/agent/
├── __init__.py    # exporta create_agent_graph()
├── state.py       # AgentState TypedDict
├── nodes.py       # funções dos nós: generate_sql, execute_sql, interpret_result, handle_error
└── graph.py       # StateGraph + edges condicionais + compilação
```

**Grafo:**
```
START
  │
  ▼
generate_sql  ──→  execute_sql
                       │
                  SQL_ERROR?
                  ├─ retry_count < 2 → generate_sql (erro injetado no contexto)
                  └─ retry_count >= 2 → handle_error
                       │
                  success → interpret_result
                       │
                       ▼
                      END
```

**AgentState:**
```python
class AgentState(TypedDict):
    question: str       # pergunta original do usuário
    schema: str         # DDL injetado no on_chat_start via SqlSchemaTool
    sql: str            # SQL gerado pelo nó generate_sql
    sql_result: str     # resultado do SqlExecuteTool (markdown table ou SQL_ERROR:...)
    retry_count: int    # tentativas consumidas (0, 1 ou 2)
    error: str | None   # último erro SQL para contexto no retry
    analysis: str       # análise financeira final (output de interpret_result)
```

**Alternativa rejeitada:**
- **`graph.py` único** — estado, nós e grafo no mesmo arquivo. Mais simples, mas dificulta testes unitários dos nós individualmente.

---

## 4. Integração com `app.py`

### `on_chat_start` — uma vez por sessão Chainlit
```python
@cl.on_chat_start
async def on_chat_start() -> None:
    schema = SqlSchemaTool()._run("")
    sql_prompt = get_sql_prompt().partial(schema=schema)
    graph = create_agent_graph(sql_prompt)
    cl.user_session.set("graph", graph)
    cl.user_session.set("schema", schema)
    await cl.Message(content="Olá! Sou o FinLake Analyst...").send()
```

### `on_message` — por pergunta do usuário
```python
@cl.on_message
async def on_message(message: cl.Message) -> None:
    graph = cl.user_session.get("graph")
    schema = cl.user_session.get("schema")

    msg = cl.Message(content="")
    async for event in graph.astream_events(
        {"question": message.content, "schema": schema,
         "sql": "", "sql_result": "", "retry_count": 0,
         "error": None, "analysis": ""},
        version="v2",
    ):
        if (
            event["event"] == "on_chat_model_stream"
            and event["metadata"].get("langgraph_node") == "interpret_result"
        ):
            chunk = event["data"]["chunk"]
            if chunk.content:
                await msg.stream_token(chunk.content)
    await msg.send()
```

---

## 5. Amostras para Grounding

As 5 queries validadas do SQL_TOOL (P1–P5) definem os padrões de consulta esperados:

| Query | Padrão | Tabela |
|---|---|---|
| P1 | Ranking por alpha_selic com filtro outliers | gold_cvm.fundo_mensal |
| P2 | Agregação de captação por período | gold_cvm.fundo_mensal |
| P3 | Série temporal SELIC (interval) | gold_bcb.macro_mensal |
| P4 | PL médio por tipo de fundo (GROUP BY) | gold_cvm.fundo_mensal |
| P5 | Join implícito BCB/CVM via taxa_anual_bcb | gold_cvm.fundo_mensal |

---

## 6. YAGNI — O que foi removido e por quê

| Removido | Motivo |
|---|---|
| LangFuse callbacks | Feature OBSERVABILITY — não bloqueia o agente funcionar; será adicionado sobre o grafo pronto |
| Memória de conversa (histórico de mensagens) | v1 stateless por design; cada pergunta é independente. Adicionar histórico exige mudança no AgentState e nos prompts |
| Nó de clarificação de ambiguidade | Complexidade de grafo para v1; o agente tenta responder com o que tem |
| Autenticação Chainlit | Já configurado via `CHAINLIT_AUTH_SECRET` no `.env`; não é responsabilidade do agente |
| Nó de validação SQL antes da execução (LLM-based) | Rejeitado no SQL_TOOL brainstorm: `sql_db_query_checker` adiciona latência sem ganho mensurável |
| DeepEval integrado ao grafo | Feature separada; avaliação offline, não inline |
| Indicador "pensando..." durante SQL generation | Nice-to-have de UX; pode ser adicionado sem mudar a arquitetura do grafo |

---

## 7. Rascunho de Requisitos para /define

### Funcionais
- [ ] Criar `agent/state.py` com `AgentState(TypedDict)`
- [ ] Criar `agent/nodes.py` com funções `generate_sql`, `execute_sql`, `interpret_result`, `handle_error`
- [ ] Criar `agent/graph.py` com `StateGraph`, edges condicionais de retry, e `create_agent_graph()` compilado
- [ ] Exportar `create_agent_graph()` via `agent/__init__.py`
- [ ] Atualizar `app.py`: `on_chat_start` injeta schema + compila grafo; `on_message` executa com streaming
- [ ] Filtrar streaming por `langgraph_node == "interpret_result"` — SQL nunca exibido ao usuário
- [ ] `handle_error` retorna mensagem em português quando `retry_count >= 2`
- [ ] `generate_sql` injeta o erro anterior no contexto quando `retry_count > 0`

### Não-funcionais
- [ ] `AgentState` usa `TypedDict` (LangGraph nativo, sem Pydantic)
- [ ] LLM instanciado via `ChatAnthropic(model=settings.model_name)`
- [ ] Testes unitários dos nós com mock do LLM e das tools
- [ ] `create_agent_graph()` aceita `sql_prompt` como parâmetro (injeção de dependência para testabilidade)

---

## 8. Próximo Passo

```bash
/define .claude/sdd/features/BRAINSTORM_AGENT_CORE.md
```
