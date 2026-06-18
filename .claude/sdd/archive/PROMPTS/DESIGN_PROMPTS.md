# DESIGN: PROMPTS

> Design técnico dos dois `ChatPromptTemplate` que instruem o Claude a gerar SQL e interpretar resultados financeiros em português.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | PROMPTS |
| **Data** | 2026-06-10 |
| **Autor** | Nilton Coura |
| **DEFINE** | [DEFINE_PROMPTS.md](./DEFINE_PROMPTS.md) |
| **Status** | ✅ Shipped |

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                    PROMPTS — Posição no sistema                       │
│                                                                        │
│  on_chat_start (AGENT_CORE)                                           │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │  SqlSchemaTool._run("") ──→ schema_str                       │     │
│  │  get_sql_prompt()          ──→ sql_template                  │     │
│  │  sql_template.partial(schema=schema_str) ──→ bound_template  │     │
│  │  store bound_template in user_session                        │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                        │
│  on_message (AGENT_CORE) — por pergunta do usuário                    │
│                                                                        │
│  ┌──── Passo 1: SQL Generation ────────────────────────────────┐     │
│  │  bound_template.format_messages(question=Q) ──→ msgs        │     │
│  │  claude(msgs) ──→ sql_str (SQL puro, sem markdown)          │     │
│  │  SqlExecuteTool._run(sql_str) ──→ result_str                │     │
│  └──────────────────────────────────────────────────────────── ┘     │
│                                                                        │
│  ┌──── Passo 2: Interpretation ────────────────────────────────┐     │
│  │  get_interpretation_prompt().format_messages(               │     │
│  │      question=Q, sql=sql_str, result=result_str             │     │
│  │  ) ──→ interp_msgs                                          │     │
│  │  claude(interp_msgs) ──→ analysis_str (texto financeiro)    │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                        │
│  ┌──── prompts/ (ESTA FEATURE) ────────────────────────────────┐     │
│  │  get_sql_prompt()            → ChatPromptTemplate            │     │
│  │    input_variables: [schema, question]                       │     │
│  │  get_interpretation_prompt() → ChatPromptTemplate            │     │
│  │    input_variables: [question, sql, result]                  │     │
│  └─────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Components

| Componente | Propósito | Tecnologia |
|---|---|---|
| `sql_prompt.py` | Template para geração SQL com few-shot P1+P3+P_new e regra anti-JOIN BCB | `langchain_core.prompts.ChatPromptTemplate` |
| `interpretation_prompt.py` | Template para interpretação financeira em português | `langchain_core.prompts.ChatPromptTemplate` |
| `prompts/__init__.py` | Exporta as duas factory functions para `agent/` | Python stdlib |

---

## Key Decisions

### Decision ADR-001: Few-shot embutido no system message vs. FewShotChatMessagePromptTemplate

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-10 |

**Context:** LangChain oferece `FewShotChatMessagePromptTemplate` que estrutura exemplos few-shot como pares de mensagens (HumanMessage + AIMessage). A alternativa é embutir os exemplos diretamente como texto no system message.

**Choice:** Embutir como texto no system message.

**Rationale:** Para Text-to-SQL, o output esperado é uma string SQL — não uma "resposta de chat". Embutir exemplos como AIMessages implicaria que o modelo deve responder em formato conversacional. Texto embutido no system message é mais direto e semanticamente correto: "quando receber esta pergunta, gere este SQL". Sem diferença mensurável de acurácia para Claude 4.

**Alternatives Rejected:**
1. `FewShotChatMessagePromptTemplate` — adiciona complexidade de classes sem benefício; o formato HumanMessage/AIMessage é semânticamente errado para SQL output
2. Exemplos em arquivo `.txt` externo — adiciona leitura de arquivo em runtime; pouca flexibilidade para inline edits

**Consequences:**
- Os exemplos são parte do system message; aparecem no trace do LangFuse como parte do prompt template
- Simples para manter: editar a string `_SQL_SYSTEM` em `sql_prompt.py`

---

### Decision ADR-002: Variável `{schema}` no template vs. parâmetro `schema: str` na factory function

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-10 |

**Context:** `get_sql_prompt()` poderia aceitar `schema: str` como parâmetro e retornar um template já com o schema injetado (`input_variables = ["question"]` apenas). Ou pode retornar um template com `input_variables = ["schema", "question"]` e delegar a injeção ao AGENT_CORE.

**Choice:** Template com variável `{schema}` — `input_variables = ["schema", "question"]`.

**Rationale:** O LangFuse captura `input_variables` nos traces automaticamente. Ter `schema` como variável nomeada visível no trace permite distinguir "o que é instrução fixa" de "o que é contexto dinâmico" — invaluável para debugging de prompts. O AGENT_CORE usa `.partial(schema=schema_str)` no `on_chat_start` para pré-vincular o schema, mantendo eficiência sem sacrificar observabilidade.

**Alternatives Rejected:**
1. `get_sql_prompt(schema: str) -> ChatPromptTemplate` — oculta o schema no trace; quebra a separação entre "construção do template" e "injeção de dados"

**Consequences:**
- `get_sql_prompt()` é uma factory pura — zero side effects, zero I/O
- AGENT_CORE chama `get_sql_prompt().partial(schema=schema_str)` uma vez por sessão

---

### Decision ADR-003: Dois arquivos separados vs. `prompts.py` único

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-10 |

**Context:** Os dois templates poderiam viver em um único `prompts.py`.

**Choice:** Dois arquivos separados: `sql_prompt.py` e `interpretation_prompt.py`.

**Rationale:** Responsabilidade única por arquivo — o prompt SQL pode evoluir independentemente do de interpretação. Para AGENT_CORE (e futuramente para testes de eval), importar somente `get_sql_prompt` sem carregar o módulo de interpretação é mais explícito. Consistente com o padrão do `tools/` que também separou `sql_execute.py` de `sql_schema.py`.

**Alternatives Rejected:**
1. `prompts.py` único — viola princípio de responsabilidade única; os dois prompts têm ciclos de vida de evolução diferentes

**Consequences:**
- `__init__.py` re-exporta ambas as funções, mantendo a interface pública limpa
- Imports no AGENT_CORE: `from finlake_analyst.prompts import get_sql_prompt, get_interpretation_prompt`

---

## File Manifest

| # | Arquivo | Ação | Propósito | Dependências |
|---|---|---|---|---|
| 1 | `src/finlake_analyst/prompts/sql_prompt.py` | Criar | `get_sql_prompt()` — ChatPromptTemplate SQL generation com few-shot P1+P3+P_new | None |
| 2 | `src/finlake_analyst/prompts/interpretation_prompt.py` | Criar | `get_interpretation_prompt()` — ChatPromptTemplate interpretação financeira | None |
| 3 | `src/finlake_analyst/prompts/__init__.py` | Modificar | Exporta `get_sql_prompt`, `get_interpretation_prompt` | 1, 2 |
| 4 | `tests/test_prompts.py` | Criar | 7 testes estruturais AT-001 a AT-007 | 1, 2, 3 |

**Total:** 4 arquivos (3 novos + 1 modificado)

---

## Code Patterns

### Pattern 1 — `sql_prompt.py`

```python
"""Template ChatPromptTemplate para geração SQL — domínio financeiro brasileiro."""

from langchain_core.prompts import ChatPromptTemplate

_SQL_SYSTEM = """\
Você é um especialista em SQL PostgreSQL e análise de dados financeiros brasileiros.

Você tem acesso ao seguinte schema do banco de dados Gold:
{schema}

## Exemplos

Pergunta: "Quais fundos com maior alpha_selic no último trimestre de 2024?"
SQL:
SELECT cnpj_fundo, gestor, ano_mes, rentabilidade_mes_pct, alpha_selic
FROM gold_cvm.fundo_mensal
WHERE alpha_selic > 0
  AND rentabilidade_mes_pct < 1000
  AND ano_mes >= '2024-10-01'
ORDER BY alpha_selic DESC
LIMIT 20

Pergunta: "Como evoluiu a SELIC real nos últimos 12 meses?"
SQL:
SELECT date, taxa_anual, selic_real, ptax_media
FROM gold_bcb.macro_mensal
WHERE date >= current_date - interval '12 months'
ORDER BY date ASC

Pergunta: "Qual o alpha_selic médio dos fundos quando a taxa SELIC anual estava acima de 12%?"
SQL:
SELECT AVG(alpha_selic) AS alpha_selic_medio,
       COUNT(DISTINCT cnpj_fundo) AS qtd_fundos
FROM gold_cvm.fundo_mensal
WHERE taxa_anual_bcb > 12
  AND alpha_selic IS NOT NULL

## Regras obrigatórias

1. Retorne APENAS o SQL puro — sem blocos de código markdown (```), \
sem comentários, sem texto adicional
2. Somente queries SELECT são permitidas
3. Em queries que ordenam ou filtram diretamente POR rentabilidade_mes_pct, \
sempre filtre: rentabilidade_mes_pct < 1000 (outliers por erro de cadastro CVM). \
Não aplique esse filtro em queries que não usam essa coluna como critério
4. alpha_selic e alpha_ipca estão disponíveis apenas até 2024-12; \
para 2025+ esses campos estarão nulos
5. Não utilize a tabela fundo_diario — use fundo_mensal para análises de fundos
6. Adicione LIMIT 50 quando o usuário não especificar quantidade
7. As colunas taxa_anual_bcb, acumulado_12m_ipca, alpha_selic e alpha_ipca já \
trazem dados do domínio BCB pré-calculados dentro de gold_cvm.fundo_mensal. \
NUNCA faça JOIN com gold_bcb quando a pergunta envolver fundos e indicadores \
macroeconômicos (SELIC, IPCA) ao mesmo tempo — use essas colunas diretamente\
"""

_SQL_HUMAN = "{question}"


def get_sql_prompt() -> ChatPromptTemplate:
    """Retorna template para geração de SQL a partir de pergunta em linguagem natural."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", _SQL_SYSTEM),
            ("human", _SQL_HUMAN),
        ]
    )
```

> **Nota de implementação:** As strings de template têm `\` no final de linhas longas para caber em 100 chars (ruff `E501`). A barra invertida dentro de strings Python é continuação de linha, não newline no output.

---

### Pattern 2 — `interpretation_prompt.py`

```python
"""Template ChatPromptTemplate para interpretação financeira dos resultados SQL."""

from langchain_core.prompts import ChatPromptTemplate

_INTERPRETATION_SYSTEM = """\
Você é um analista financeiro sênior brasileiro especializado em fundos de investimento \
e macroeconomia.

Contexto de mercado:
- SELIC: taxa básica de juros do Brasil, principal benchmark de renda fixa
- CDI: certificado de depósito interbancário, proxy do SELIC para fundos
- Alpha: excesso de retorno de um fundo sobre seu benchmark \
(ex: alpha_selic = rentabilidade - SELIC)
- Rentabilidade positiva acima do CDI indica desempenho superior à renda fixa básica

Ao interpretar os dados:
- Use números concretos do resultado fornecido
- Contextualize em relação ao cenário brasileiro (nível da SELIC, mercado de fundos)
- Seja conciso: 2 a 4 parágrafos
- Escreva em português brasileiro, sem jargão desnecessário
- Não repita o SQL executado nem os dados brutos em formato de tabela\
"""

_INTERPRETATION_HUMAN = """\
Pergunta original: {question}

SQL executado:
{sql}

Resultado da consulta:
{result}

Forneça uma análise financeira concisa em português.\
"""


def get_interpretation_prompt() -> ChatPromptTemplate:
    """Retorna template para interpretação financeira de resultados SQL."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", _INTERPRETATION_SYSTEM),
            ("human", _INTERPRETATION_HUMAN),
        ]
    )
```

---

### Pattern 3 — `prompts/__init__.py`

```python
"""Templates de prompt Text-to-SQL e interpretação financeira brasileira."""

from finlake_analyst.prompts.interpretation_prompt import get_interpretation_prompt
from finlake_analyst.prompts.sql_prompt import get_sql_prompt

__all__ = ["get_sql_prompt", "get_interpretation_prompt"]
```

---

### Pattern 4 — `tests/test_prompts.py`

```python
"""Testes estruturais dos templates de prompt — sem banco de dados ou API."""

import pytest
from langchain_core.prompts import ChatPromptTemplate

from finlake_analyst.prompts import get_interpretation_prompt, get_sql_prompt


def test_sql_prompt_returns_chat_prompt_template() -> None:
    """get_sql_prompt() retorna uma instância de ChatPromptTemplate."""
    assert isinstance(get_sql_prompt(), ChatPromptTemplate)


def test_sql_prompt_input_variables() -> None:
    """SQL prompt tem exatamente as variáveis {schema} e {question}."""
    assert set(get_sql_prompt().input_variables) == {"schema", "question"}


def test_interpretation_prompt_returns_chat_prompt_template() -> None:
    """get_interpretation_prompt() retorna uma instância de ChatPromptTemplate."""
    assert isinstance(get_interpretation_prompt(), ChatPromptTemplate)


def test_interpretation_prompt_input_variables() -> None:
    """Interpretation prompt tem exatamente {question}, {sql} e {result}."""
    assert set(get_interpretation_prompt().input_variables) == {"question", "sql", "result"}


def test_sql_prompt_contains_fewshot_p1() -> None:
    """SQL prompt formatado contém o exemplo P1 (alpha_selic — tabela CVM)."""
    messages = get_sql_prompt().format_messages(schema="<ddl>", question="teste")
    assert "alpha_selic" in messages[0].content


def test_sql_prompt_contains_fewshot_p3() -> None:
    """SQL prompt formatado contém o exemplo P3 (SELIC real — tabela BCB)."""
    messages = get_sql_prompt().format_messages(schema="<ddl>", question="teste")
    system_content = messages[0].content
    assert "selic_real" in system_content or "interval" in system_content


def test_sql_prompt_prohibits_markdown_blocks() -> None:
    """SQL prompt instrui explicitamente a não usar blocos markdown."""
    messages = get_sql_prompt().format_messages(schema="<ddl>", question="teste")
    system_content = messages[0].content
    assert "sem blocos" in system_content


def test_interpretation_prompt_references_financial_context() -> None:
    """Interpretation prompt referencia contexto financeiro brasileiro."""
    messages = get_interpretation_prompt().format_messages(
        question="q", sql="SELECT 1", result="r"
    )
    system_content = messages[0].content
    assert any(kw in system_content for kw in ["SELIC", "CDI", "benchmark"])
```

> **Nota:** `test_sql_prompt_prohibits_markdown_blocks` verifica a substring `"sem blocos"` que é parte literal da Regra 1 no `_SQL_SYSTEM`. Se o texto da regra mudar, o teste precisará ser atualizado em conjunto.

---

## Data Flow

```text
AGENT_CORE — on_chat_start:
  1. SqlSchemaTool._run("") → schema_str
     │
  2. get_sql_prompt() → sql_template           ← PROMPTS
     │
  3. sql_template.partial(schema=schema_str) → bound_sql_template
     │
  4. store(bound_sql_template) em user_session

AGENT_CORE — on_message(question):
  ┌─ Passo 1: SQL Generation ─────────────────────────────────────────┐
  │ 5. bound_sql_template.format_messages(question=Q) → sql_messages  │
  │ 6. llm.invoke(sql_messages) → AIMessage(content=sql_str)          │
  │ 7. SqlExecuteTool._run(sql_str) → result_str                      │
  │    └─ se SQL_ERROR: ciclo ReAct de correção (AGENT_CORE)          │
  └───────────────────────────────────────────────────────────────────┘
  ┌─ Passo 2: Interpretation ─────────────────────────────────────────┐
  │ 8. get_interpretation_prompt() → interp_template ← PROMPTS        │
  │ 9. interp_template.format_messages(                               │
  │        question=Q, sql=sql_str, result=result_str                 │
  │    ) → interp_messages                                             │
  │10. llm.invoke(interp_messages) → AIMessage(content=analysis_str) │
  │11. cl.Message(content=analysis_str).send()                        │
  └───────────────────────────────────────────────────────────────────┘
```

---

## Integration Points

| Sistema Externo | Tipo de Integração | Notas |
|---|---|---|
| LangChain Core | `ChatPromptTemplate` | `langchain-core` já em `pyproject.toml` |
| LangGraph / AGENT_CORE | Consumidor dos templates | Chama `get_sql_prompt()` e `get_interpretation_prompt()` |
| LangFuse | Observabilidade automática | Captura `input_variables` e mensagens formatadas via LangGraph callbacks |
| Anthropic Claude | LLM invocado pelo AGENT_CORE | Os templates geram as mensagens que são enviadas ao Claude |

---

## Testing Strategy

| Tipo | Escopo | Arquivo | Ferramentas | Meta |
|---|---|---|---|---|
| Unit | Estrutura e conteúdo dos templates | `tests/test_prompts.py` | pytest, string matching | 8/8 ATs |
| Integration | Templates formatados + LLM | Manual / AGENT_CORE | Chainlit | Happy path na entrega do AGENT_CORE |

**Cobertura dos Acceptance Tests:**

| AT | Teste | Verificação |
|---|---|---|
| AT-001 | `test_sql_prompt_input_variables` | `{"schema", "question"}` |
| AT-002 | `test_interpretation_prompt_input_variables` | `{"question", "sql", "result"}` |
| AT-003 | `test_sql_prompt_contains_fewshot_p1` | `"alpha_selic"` no system |
| AT-004 | `test_sql_prompt_contains_fewshot_p3` | `"selic_real"` ou `"interval"` |
| AT-005 | `test_sql_prompt_prohibits_markdown_blocks` | `"sem blocos"` |
| AT-006 | `test_interpretation_prompt_references_financial_context` | `"SELIC"`, `"CDI"` ou `"benchmark"` |
| AT-007 | `test_sql_prompt_returns_chat_prompt_template` + `test_interpretation_prompt_returns_chat_prompt_template` | `isinstance(..., ChatPromptTemplate)` |

---

## Error Handling

| Cenário | Tratamento |
|---|---|
| Variável não preenchida no template | LangChain levanta `KeyError` com nome da variável — responsabilidade do AGENT_CORE preencher todas as variáveis antes de invocar |
| `{schema}` contém `{...}` literal (ex: JSON no DDL) | Não aplicável: o output do `SqlSchemaTool` é DDL PostgreSQL, sem chaves literais |
| Imports falham (`langchain-core` ausente) | `ImportError` em runtime — `langchain-core` é dependência transitiva de `langchain`; garantido no `pyproject.toml` |

---

## Configuration

Nenhuma — os templates são constantes Python. Não há configuração via `Settings`. O conteúdo dos prompts é code, não config: mudanças requerem review de código, o que é o comportamento desejado para prompts de produção.

---

## Security Considerations

- Prompt injection: o campo `{question}` é fornecido pelo usuário. O system prompt não tem instruções privilegiadas que um usuário poderia tentar sobreescrever. O Claude não tem acesso a dados fora do que `SqlExecuteTool` retorna — a superfície de ataque é mínima.
- Os templates não executam código — são strings Python. Zero risco de execução arbitrária na construção do prompt.

---

## Observabilidade

| Aspecto | Implementação |
|---|---|
| Prompt templates | LangFuse captura automaticamente via LangGraph callbacks — sem instrumentação manual necessária |
| Variáveis injetadas | `schema`, `question`, `sql`, `result` aparecem como `inputs` no trace do LangFuse |
| Latência por passo | LangFuse registra latência separada para cada `llm.invoke()` — visível por passo |

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-10 | Nilton Coura | Versão inicial |
| 1.1 | 2026-06-18 | Nilton Coura | Regra 3 estreitada (outlier só quando query usa `rentabilidade_mes_pct` como critério); Regra 7 adicionada (anti-JOIN BCB via colunas denormalizadas); terceiro few-shot P_new (`taxa_anual_bcb > 12`) — eval_sql.py: 3/5 → 5/5 (commits e83f68d e c464a4d) |

---

## Next Step

**Pronto para:** `/build .claude/sdd/features/DESIGN_PROMPTS.md`
