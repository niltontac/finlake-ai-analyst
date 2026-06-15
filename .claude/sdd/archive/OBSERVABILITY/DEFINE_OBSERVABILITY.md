# DEFINE: OBSERVABILITY

> LangFuse traces com metadata enriquecida + script DeepEval de avaliação SQL para o agente Text-to-SQL.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | OBSERVABILITY |
| **Data** | 2026-06-12 |
| **Autor** | Nilton Coura |
| **Status** | ✅ Shipped |
| **Clarity Score** | 14/15 |

---

## Problem Statement

O agente Text-to-SQL está funcional mas completamente cego em produção: erros de SQL são silenciosos do ponto de vista do desenvolvedor, retries acontecem sem rastreabilidade, o custo por pergunta é desconhecido e a qualidade do SQL gerado nunca foi mensurada. Sem observabilidade, é impossível saber se o agente está se comportando bem, quais perguntas causam mais retries, ou se mudanças nos prompts melhoram ou pioram a qualidade.

---

## Target Users

| Usuário | Papel | Pain Point |
|---|---|---|
| Nilton Coura | Desenvolvedor / operador | Não consegue debugar comportamento do agente nem medir qualidade sem instrumentação |

---

## Goals

### LangFuse — Traces

| Prioridade | Goal |
|---|---|
| **MUST** | Criar `CallbackHandler` por mensagem em `on_message` com `session_id` (Chainlit session) e `question` como metadata inicial |
| **MUST** | Passar handler via `config={"callbacks": [lf_handler]}` em `graph.astream_events` |
| **MUST** | Capturar `final_sql` do evento `on_chain_end` do nó `generate_sql` durante o loop de eventos |
| **MUST** | Capturar `final_retry_count` do evento `on_chain_end` do nó `execute_sql` durante o loop de eventos |
| **MUST** | Após o loop: enriquecer a trace LangFuse com `final_sql` e `final_retry_count` como metadata |
| **MUST** | Chamar flush/shutdown do handler para garantir envio antes do Chainlit finalizar a resposta |
| **MUST** | Falhas do LangFuse (credenciais inválidas, timeout, rede) não devem impedir o agente de responder |

### DeepEval — Script de Evals

| Prioridade | Goal |
|---|---|
| **MUST** | Criar `evals/` como package (`evals/__init__.py`) |
| **MUST** | Criar `evals/eval_sql.py` com 5 test cases P1–P5 (perguntas + SQL esperado hardcoded) |
| **MUST** | Implementar `GEval` com critério de equivalência semântica SQL como métrica |
| **MUST** | Script executável com `uv run python evals/eval_sql.py` |
| **MUST** | Output no terminal: score numérico por query (P1–P5) + score geral + pass/fail |
| **SHOULD** | Script imprime quais queries falharam com score < threshold para facilitar debugging |

---

## Success Criteria

- [ ] `from langfuse.callback import CallbackHandler` importa sem erro
- [ ] `graph.astream_events(state, config={"callbacks": [lf_handler]}, version="v2")` executa sem exceção
- [ ] Após executar uma pergunta no Chainlit, o trace aparece no LangFuse Cloud com `final_sql` e `retry_count` na metadata
- [ ] Exceção lançada pelo LangFuse (ex: `LANGFUSE_HOST` inválido) é capturada e o agente responde normalmente
- [ ] `uv run python evals/eval_sql.py` executa até o fim sem `ImportError` ou `ModuleNotFoundError`
- [ ] Output do script contém score numérico para cada uma das 5 queries (P1–P5)
- [ ] `ruff check src/ evals/` zero violations
- [ ] Nenhum teste pytest existente quebra (regressão)

---

## Acceptance Tests

| ID | Cenário | Given | When | Then |
|---|---|---|---|---|
| AT-001 | Import do CallbackHandler funciona | Pacote `langfuse>=2.0` instalado | `from langfuse.callback import CallbackHandler` | Sem `ImportError` |
| AT-002 | Handler criado com settings reais | `Settings` carregado do `.env` | `CallbackHandler(public_key=..., secret_key=..., host=..., session_id="test")` | Instância criada sem exceção |
| AT-003 | `final_sql` capturado do evento `generate_sql` | `on_chain_end` com `node == "generate_sql"` e output `{"sql": "SELECT 1"}` | Lógica de captura no loop de eventos | `final_sql == "SELECT 1"` |
| AT-004 | `final_retry_count` capturado do evento `execute_sql` | `on_chain_end` com `node == "execute_sql"` e output `{"retry_count": 1}` | Lógica de captura no loop de eventos | `final_retry_count == 1` |
| AT-005 | Falha do LangFuse não quebra agente | `CallbackHandler` com host inválido | Usuário envia pergunta, agente processa | Resposta chega ao usuário; exceção do LangFuse logada, não propagada |
| AT-006 | Script de evals importa sem erro | `uv run python evals/eval_sql.py` | Execução no terminal | Sem `ImportError`; script inicia |
| AT-007 | Script gera SQL para P1–P5 | `.env` com `DATABASE_URL` e `ANTHROPIC_API_KEY` válidos | `graph.ainvoke` para cada test case | 5 SQLs gerados e capturados em `state["sql"]` |
| AT-008 | Output inclui score numérico por query | Evals executadas | Terminal | Output contém 5 linhas com `P1`, `P2`, `P3`, `P4`, `P5` e respectivos scores |
| AT-009 | `GEval` instancia sem erro | `deepeval>=1.4` instalado | `GEval(name=..., criteria=..., evaluation_params=[...])` | Instância criada sem exceção |

---

## Out of Scope

- LangFuse prompt versioning — não é objetivo de OBSERVABILITY; pertence a uma futura feature de prompt management
- DeepEval métricas de resposta final (`AnswerRelevancy`, `Faithfulness`) — usuário escolheu SQL only; análise final é avaliada manualmente
- DeepEval integração com pytest ou CI/CD — custo de API por build inaceitável; usuário escolheu script standalone
- LangFuse custom dashboards — UI padrão do LangFuse Cloud é suficiente para v1
- `user_id` nos traces — Chainlit não tem autenticação de usuário configurada; `session_id` é suficiente
- DeepEval alertas automáticos ou score targets — threshold de 0.7 como padrão; sem notificações

---

## Constraints

| Tipo | Constraint | Impacto |
|---|---|---|
| Técnico | `langfuse>=2.0` já em `dependencies`; `deepeval>=1.4` em `dev` | Não adicionar novas dependências; usar o que está instalado |
| Técnico | Python 3.12, type hints obrigatórios, docstrings públicas | Arquivos novos seguem convenções finlake-brasil |
| Técnico | `src/` layout e `evals/` como novo package na raiz | `evals/` fica fora de `src/` — é ferramenta de desenvolvimento, não código de produção |
| Técnico | `ruff check src/ evals/` deve passar | `evals/` incluído no linting |
| Comportamento | LangFuse indisponível não pode quebrar o agente | Envolver criação/uso do handler em `try/except` no `on_message` |
| Dados | SQL esperado P1–P5 é ground truth imutável | Não modificar os SQLs do SQL_TOOL archive |

---

## Technical Context

| Aspecto | Valor | Notas |
|---|---|---|
| **Deployment Location** | `src/finlake_analyst/app.py` (LangFuse) + `evals/eval_sql.py` (DeepEval) | `app.py` modificado; `evals/` package novo |
| **LangFuse version** | `langfuse>=2.0` (instalado: verificar com `uv pip show langfuse`) | API `CallbackHandler` pode variar; validar A-001/A-002 no início do Build |
| **DeepEval version** | `deepeval>=1.4` (instalado: verificar com `uv pip show deepeval`) | `GEval` disponível desde 1.0; validar A-005 no início do Build |
| **IaC Impact** | None | Credenciais LangFuse já em `.env`; sem nova infraestrutura |

---

## Assumptions a Validar no Início do Build

| ID | Assumption | Validação |
|---|---|---|
| A-001 | `CallbackHandler` expõe atributo para enriquecer a trace após execução (ex: `.langfuse`, `.trace_id`) | `python -c "from langfuse.callback import CallbackHandler; print([a for a in dir(CallbackHandler('pk','sk')) if not a.startswith('__')])"` |
| A-002 | `config={"callbacks": [handler]}` em `astream_events` é suportado pelo LangGraph 1.2.4 | Smoke test com `LANGFUSE_DEBUG=true` e verificação de traces no dashboard |
| A-003 | `event["data"]["output"]["sql"]` está disponível no `on_chain_end` do nó `generate_sql` (validação do AGENT_CORE pendente) | Rodar o smoke script do AGENT_CORE; inspecionar eventos |
| A-004 | `event["data"]["output"]["retry_count"]` está disponível no `on_chain_end` do nó `execute_sql` | Idem |
| A-005 | `GEval` com `evaluation_params=[LLMTestCaseParams.EXPECTED_OUTPUT]` disponível no DeepEval 1.4 | `python -c "from deepeval.metrics import GEval; from deepeval.test_case import LLMTestCaseParams; print('ok')"` |

---

## Interface dos Componentes

### LangFuse — padrão em `app.py`

```python
# Criação do handler (por mensagem):
lf_handler = CallbackHandler(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_host,
    session_id=cl.context.session.id,
    metadata={"question": message.content},
)

# Uso no astream_events:
graph.astream_events(state, config={"callbacks": [lf_handler]}, version="v2")

# Captura durante o loop:
# on_chain_end + node=="generate_sql" → final_sql
# on_chain_end + node=="execute_sql" → final_retry_count

# Enriquecimento após o loop:
# Atualizar trace com final_sql e final_retry_count (API exata a validar em A-001/A-002)
```

### DeepEval — estrutura de `evals/eval_sql.py`

```python
# 5 TEST CASES hardcoded (P1-P5):
TEST_CASES = [
    {"id": "P1", "question": "Quais fundos com maior alpha_selic no último trimestre de 2024?",
     "expected_sql": "SELECT cnpj_fundo, gestor, ..."},
    # P2-P5 idem
]

# MÉTRICA GEval:
sql_correctness = GEval(
    name="SQL Correctness",
    criteria="O SQL gerado é semanticamente equivalente ao SQL esperado ...",
    evaluation_params=[INPUT, ACTUAL_OUTPUT, EXPECTED_OUTPUT],
    threshold=0.7,
)

# FLUXO PRINCIPAL:
# 1. Criar graph via create_agent_graph(sql_prompt)
# 2. Para cada test case: graph.ainvoke(state) → state["sql"]
# 3. Criar LLMTestCase(input=question, actual_output=sql, expected_output=expected_sql)
# 4. deepeval.evaluate([test_cases], [sql_correctness])
# 5. Imprimir resultados
```

---

## Clarity Score Breakdown

| Elemento | Score (0-3) | Notas |
|---|---|---|
| Problem | 3 | Específico: erros silenciosos, custo desconhecido, qualidade não mensurada |
| Users | 2 | Um persona claro (Nilton/dev); usuário final não é relevante nesta feature |
| Goals | 3 | 13 goals MoSCoW divididos entre LangFuse/DeepEval, interfaces de código especificadas |
| Success | 3 | 8 critérios testáveis: imports, trace com metadata, script executa, score impresso |
| Scope | 3 | 6 itens fora de escopo + 5 assumptions explícitas com como validar |
| **Total** | **14/15** | Passa o gate (12/15) |

---

## Open Questions

- **A-001/A-002**: A API exata para enriquecer a trace LangFuse após o loop é a principal incerteza. Dependendo do que o `CallbackHandler` expõe, pode ser necessário usar o SDK LangFuse diretamente (criar cliente `Langfuse()` separado para o update). A validação desses dois assumptions é o primeiro passo do Build.

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-12 | Nilton Coura | Versão inicial gerada a partir de BRAINSTORM_OBSERVABILITY.md |

---

## Next Step

**Pronto para:** `/design .claude/sdd/features/DEFINE_OBSERVABILITY.md`
