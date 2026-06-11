# DEFINE: PROMPTS

> Dois `ChatPromptTemplate` que instruem o Claude a gerar SQL e interpretar resultados financeiros em português.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | PROMPTS |
| **Data** | 2026-06-10 |
| **Autor** | Nilton Coura |
| **Status** | ✅ Shipped |
| **Clarity Score** | 14/15 |

---

## Problem Statement

O agente LangGraph não tem prompts definidos — sem eles, o AGENT_CORE não consegue instruir o Claude a gerar SQL correto sobre os schemas Gold nem a interpretar os resultados financeiramente em português brasileiro. A feature PROMPTS preenche essa lacuna com dois templates especializados que o agente usa em sequência: primeiro para gerar SQL, depois para interpretar o resultado.

---

## Target Users

| Usuário | Papel | Pain Point |
|---|---|---|
| Nilton Coura | Desenvolvedor / dono do projeto | Precisa de templates testáveis, reutilizáveis e integráveis ao LangGraph/LangFuse |
| Agente LangGraph | Consumidor dos templates | Precisa de prompts que resultem em SQL PostgreSQL correto + análise financeira relevante em português |

---

## Goals

| Prioridade | Goal |
|---|---|
| **MUST** | Criar `get_sql_prompt() -> ChatPromptTemplate` com few-shot (P1 + P3), variáveis `{schema}` e `{question}` |
| **MUST** | Criar `get_interpretation_prompt() -> ChatPromptTemplate` com variáveis `{question}`, `{sql}`, `{result}` |
| **MUST** | SQL prompt instrui explicitamente: retornar apenas SQL puro — sem blocos ` ```sql``` `, sem comentários, sem texto adicional |
| **MUST** | Exportar ambas as funções via `prompts/__init__.py` para consumo pelo `agent/` |
| **SHOULD** | SQL prompt inclui regras de domínio: filtro outliers `rentabilidade_mes_pct < 1000`, limitação `alpha_selic` até 2024-12, `fundo_diario` indisponível, LIMIT padrão |
| **SHOULD** | Interpretation prompt emite análise concisa em 2-4 parágrafos com contexto de mercado brasileiro (SELIC, CDI, alpha) |
| **COULD** | Testes unitários verificam `input_variables` e substrings críticas nos prompts formatados |

---

## Success Criteria

- [ ] `get_sql_prompt().input_variables` contém exatamente `["schema", "question"]`
- [ ] `get_interpretation_prompt().input_variables` contém exatamente `["question", "sql", "result"]`
- [ ] SQL prompt formatado (com schema e question de teste) contém os dois few-shot examples — strings de P1 (`alpha_selic`) e P3 (`interval '12 months'` ou `selic_real`)
- [ ] SQL prompt formatado contém instrução explícita contra markdown code blocks (substring `sql` em contexto de negação ou equivalente)
- [ ] Interpretation prompt formatado contém papel de analista financeiro e referência a SELIC ou CDI
- [ ] `ruff check src/` zero violations nos arquivos novos
- [ ] `pytest tests/test_prompts.py` passa sem conexão ao banco ou API

---

## Acceptance Tests

| ID | Cenário | Given | When | Then |
|---|---|---|---|---|
| AT-001 | SQL prompt tem variáveis corretas | Template instanciado | `get_sql_prompt().input_variables` | Contém `"schema"` e `"question"` |
| AT-002 | Interpretation prompt tem variáveis corretas | Template instanciado | `get_interpretation_prompt().input_variables` | Contém `"question"`, `"sql"`, `"result"` |
| AT-003 | SQL prompt formatado contém few-shot P1 | Template com `schema="<ddl>"`, `question="teste"` | `.format_messages()` | Output contém `"alpha_selic"` (P1) |
| AT-004 | SQL prompt formatado contém few-shot P3 | Template com `schema="<ddl>"`, `question="teste"` | `.format_messages()` | Output contém `"selic_real"` ou `"interval"` (P3) |
| AT-005 | SQL prompt instrui SQL puro sem markdown | Template formatado | Inspeção do system message | Contém substring que proíbe blocos markdown / code fences |
| AT-006 | Interpretation prompt referencia contexto financeiro | Template formatado | Inspeção do system message | Contém `"SELIC"` ou `"CDI"` ou `"benchmark"` |
| AT-007 | `prompts/__init__.py` exporta ambas as funções | `from finlake_analyst.prompts import ...` | Import das duas funções | Sem `ImportError`; ambas retornam `ChatPromptTemplate` |

---

## Out of Scope

- Prompt de tratamento de erro SQL (`"SQL_ERROR: ..."`) — responsabilidade do AGENT_CORE via grafo LangGraph
- Prompt de clarificação de ambiguidade ao usuário — AGENT_CORE decide quando pedir esclarecimento
- Versões multilíngue (EN/PT) — 100% português brasileiro em v1
- Prompt de sumário/memória de conversa — AGENT_CORE não tem memória persistente em v1
- Configuração de temperatura, `max_tokens` ou modelo no prompt — responsabilidade do AGENT_CORE ao instanciar o LLM
- Few-shot com todas as 5 queries validadas — P1 + P3 cobrem os dois schemas (CVM + BCB); P2, P4, P5 ficam como referência de domínio

---

## Constraints

| Tipo | Constraint | Impacto |
|---|---|---|
| Técnico | Python 3.12, type hints obrigatórios, docstrings em módulos/classes/funções públicas | Todos os arquivos novos seguem convenções do finlake-brasil |
| Técnico | `langchain-core>=0.3` (já em `pyproject.toml` como dependência transitiva de `langchain`) | Usar `ChatPromptTemplate` de `langchain_core.prompts` — sem dependências novas |
| Técnico | `src/` layout | Novos arquivos em `src/finlake_analyst/prompts/` |
| Técnico | Testes sem conexão real ao banco ou API | AT-001 a AT-007 são puramente estruturais e de string matching |
| Domínio | Few-shot examples devem usar queries validadas do SQL_TOOL brainstorm | P1 e P3 são ground truth contra o banco real |

---

## Technical Context

| Aspecto | Valor | Notas |
|---|---|---|
| **Deployment Location** | `src/finlake_analyst/prompts/` | `sql_prompt.py`, `interpretation_prompt.py`, `__init__.py` |
| **KB Domains** | `ai-data-engineering/llmops-patterns`, `python/clean-architecture` | Padrões de prompt engineering LangChain e arquitetura limpa Python |
| **IaC Impact** | None | Sem nova infraestrutura; prompts são código Python puro |

---

## Interface dos Templates

### `get_sql_prompt() -> ChatPromptTemplate`

```python
# Estrutura esperada (ChatPromptTemplate)
# Messages: [SystemMessage, HumanMessage]
# input_variables: ["schema", "question"]
#
# SystemMessage contém:
#   - Papel: analista de dados financeiros brasileiros, especialista SQL PostgreSQL
#   - Schema dinâmico: {schema} (DDL + amostras + notas de qualidade do SqlSchemaTool)
#   - Few-shot P1: pergunta alpha_selic → SQL com filtro rentabilidade_mes_pct < 1000
#   - Few-shot P3: pergunta SELIC → SQL com interval '12 months'
#   - Regras: SQL puro sem markdown, apenas SELECT, filtros de qualidade, LIMIT padrão
#
# HumanMessage: "{question}"
```

### `get_interpretation_prompt() -> ChatPromptTemplate`

```python
# Estrutura esperada (ChatPromptTemplate)
# Messages: [SystemMessage, HumanMessage]
# input_variables: ["question", "sql", "result"]
#
# SystemMessage contém:
#   - Papel: analista financeiro sênior brasileiro
#   - Contexto: SELIC como benchmark, CDI como referência renda fixa, alpha = excesso de retorno
#   - Tom: conciso, direto, 2-4 parágrafos, sem markdown excessivo
#
# HumanMessage:
#   "Pergunta original: {question}
#    SQL executado: {sql}
#    Resultado da consulta:
#    {result}
#    Forneça uma análise financeira concisa em português."
```

---

## Assumptions

| ID | Suposição | Se Errada, Impacto | Validado? |
|---|---|---|---|
| A-001 | `ChatPromptTemplate.from_messages()` aceita strings Python com `{variable}` para interpolação de variáveis | Templates precisariam de outro mecanismo de interpolação | [x] Padrão LangChain documentado |
| A-002 | O AGENT_CORE vai chamar `get_sql_prompt().format_messages(schema=..., question=...)` para montar o input do LLM | Interface de consumo diferente quebraria a integração | [ ] Validar no AGENT_CORE |
| A-003 | Os few-shot examples (P1, P3) não vão conflitar com o schema dinâmico `{schema}` se as queries referenciarem `gold_cvm.` e `gold_bcb.` explicitamente | Agente geraria SQL com prefixo de schema errado | [x] P1 e P3 já usam nomes qualificados |

---

## Clarity Score Breakdown

| Elemento | Score (0-3) | Notas |
|---|---|---|
| Problem | 3 | Específico: agente sem prompts não instrui LLM a gerar SQL nem interpretar resultados |
| Users | 2 | Nilton (dev) + agente LangGraph como consumidor — único persona humano |
| Goals | 3 | 7 goals MoSCoW, interface das funções factory especificada com variáveis e comportamento |
| Success | 3 | 7 critérios testáveis via `input_variables`, string matching nos prompts formatados |
| Scope | 3 | 6 itens fora de escopo explícitos + interface de ambos os templates documentada |
| **Total** | **14/15** | Passa o gate (12/15) |

---

## Open Questions

Nenhuma — pronto para Design.

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-10 | Nilton Coura | Versão inicial gerada a partir de BRAINSTORM_PROMPTS.md |
| 1.1 | 2026-06-10 | ship-agent | Shipped and archived |

---

## Next Step

**Pronto para:** `/design .claude/sdd/features/DEFINE_PROMPTS.md`
