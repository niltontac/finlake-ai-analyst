# BRAINSTORM: PROMPTS

**Projeto:** finlake-ai-analyst  
**Data:** 2026-06-10  
**Status:** Concluído — pronto para `/define`  
**Fase:** 0 de 5 (Brainstorm)

---

## 1. Contexto

A feature **PROMPTS** implementa os dois `ChatPromptTemplate` que são o cérebro do agente Text-to-SQL do FinLake Brasil. Sem esses templates, o AGENT_CORE não tem como instruir o Claude a gerar SQL correto nem a interpretar os resultados financeiramente em português.

O fluxo do agente (estabelecido no Brainstorm) é de **dois passos**:
1. **SQL generation** — Claude recebe schema + pergunta e retorna SQL SELECT puro
2. **Interpretation** — Claude recebe pergunta + SQL + resultado e retorna análise financeira em português

A fundação está operacional: `INFRA_BASE` (config, structure) e `SQL_TOOL` (`SqlExecuteTool`, `SqlSchemaTool`) já foram entregues. O módulo `prompts/` existe como skeleton vazio.

---

## 2. Decisões Tomadas

### Q1 — Arquitetura do fluxo
**Decisão: dois passos — SQL generation → Interpretation**  
Motivo: o agente pode iterar no SQL via ReAct (gerar → executar → corrigir se SQL_ERROR) antes de interpretar. A interpretação só ocorre quando os dados já estão confirmados. Um único passo tentaria gerar SQL e interpretar simultaneamente sem saber se o SQL vai funcionar.

### Q2 — Formato dos prompts
**Decisão: `ChatPromptTemplate` com variáveis (LangChain)**  
Motivo: integração nativa com LangGraph e LangFuse — o LangFuse captura o prompt template formatado automaticamente nos traces. `ChatPromptTemplate.from_messages()` é o padrão LangChain 0.3+.

### Q3 — Injeção do schema
**Decisão: variável dinâmica `{schema}` injetada no `on_chat_start`**  
Motivo: o AGENT_CORE chama `SqlSchemaTool` uma vez por conversa e injeta o resultado no sistema prompt. Mantém o schema atual sem hardcode e o agente não precisa chamar `get_schema` em cada pergunta — o contexto já está disponível.

### Q4 — Grounding com few-shot examples
**Decisão: usar as 5 queries validadas do SQL_TOOL como base; P1 e P3 embutidas no SQL prompt**  
Motivo: Text-to-SQL é um dos casos onde few-shot supera zero-shot de forma consistente, especialmente para domínios financeiros específicos. P1 (alpha_selic ranking, tabela CVM) + P3 (evolução SELIC, tabela BCB) cobrem os dois schemas com padrões distintos.

---

## 3. Abordagem Selecionada

### Abordagem A: Few-shot SQL prompt + interpretação contextualizada ⭐ Selecionada

**Organização dos arquivos:**
```
src/finlake_analyst/prompts/
├── __init__.py                   # exporta get_sql_prompt(), get_interpretation_prompt()
├── sql_prompt.py                 # ChatPromptTemplate — geração SQL
└── interpretation_prompt.py      # ChatPromptTemplate — interpretação financeira
```

**SQL Prompt — `get_sql_prompt() -> ChatPromptTemplate`**

Variáveis: `{schema}`, `{question}`

System prompt contém:
- Papel: analista de dados financeiros brasileiros, especialista em SQL PostgreSQL
- Schema dinâmico: `{schema}` (DDL + amostras + notas de qualidade do `SqlSchemaTool`)
- 2 few-shot examples:
  - **P1** (CVM): "Quais fundos com maior alpha_selic no 4º trimestre de 2024?" → SQL com filtro `rentabilidade_mes_pct < 1000`
  - **P3** (BCB): "Como evoluiu a SELIC nos últimos 12 meses?" → SQL com `interval '12 months'`
- Regras explícitas:
  - Retornar **apenas o SQL puro** — sem blocos markdown (```sql```), sem comentários, sem explicação, sem texto adicional
  - Apenas queries SELECT
  - Filtrar `rentabilidade_mes_pct < 1000` em queries de ranking de fundos
  - `alpha_selic` e `alpha_ipca` disponíveis apenas até 2024-12 — mencionar limitação se pergunta cobrir 2025+
  - Preferir `fundo_mensal` para análises de fundos (`fundo_diario` não disponível)
  - Adicionar `LIMIT 50` quando o usuário não especificar quantidade

Human message: `{question}`

**Interpretation Prompt — `get_interpretation_prompt() -> ChatPromptTemplate`**

Variáveis: `{question}`, `{sql}`, `{result}`

System prompt contém:
- Papel: analista financeiro sênior brasileiro
- Contexto de mercado: SELIC como benchmark principal, CDI como referência de renda fixa, alpha como excesso de retorno sobre benchmark
- Tom: conciso, direto, sem jargão desnecessário, 2-4 parágrafos
- Instrução: interpretar os números em contexto de mercado brasileiro (ex: "rendimento acima do CDI", "captação positiva indica momento favorável")
- Instrução de formato: resposta em texto corrido, sem markdown excessivo, sem repetir o SQL

Human message:
```
Pergunta original: {question}
SQL executado: {sql}
Resultado da consulta:
{result}

Forneça uma análise financeira concisa em português.
```

**Alternativas rejeitadas:**
- **Zero-shot com regras** — menor acurácia em queries analíticas complexas (CTEs, joins BCB/CVM); Claude performa melhor com exemplos few-shot para Text-to-SQL em domínios específicos

---

## 4. Amostras para Grounding

### Few-shot examples embutidos no SQL Prompt

**P1 — Alpha SELIC recente (CVM — fundo_mensal)**
```
Pergunta: "Quais os fundos com maior alpha_selic no último trimestre de 2024?"
SQL:
SELECT cnpj_fundo, gestor, ano_mes, rentabilidade_mes_pct, alpha_selic
FROM gold_cvm.fundo_mensal
WHERE alpha_selic > 0
  AND rentabilidade_mes_pct < 1000
  AND ano_mes >= '2024-10-01'
ORDER BY alpha_selic DESC
LIMIT 20
```

**P3 — Evolução da SELIC (BCB — macro_mensal)**
```
Pergunta: "Como evoluiu a SELIC real nos últimos 12 meses?"
SQL:
SELECT date, taxa_anual, selic_real, ptax_media
FROM gold_bcb.macro_mensal
WHERE date >= current_date - interval '12 months'
ORDER BY date ASC
```

### Queries disponíveis como referência de domínio (não embutidas no prompt v1)

**P2 — Maior captação líquida em 2024**
```sql
SELECT cnpj_fundo, gestor, tp_fundo,
       SUM(captacao_liquida_acumulada) AS captacao_total
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY cnpj_fundo, gestor, tp_fundo
ORDER BY captacao_total DESC
LIMIT 10;
```

**P4 — PL médio por tipo de fundo**
```sql
SELECT tp_fundo,
       AVG(vl_patrim_liq_medio) AS pl_medio,
       COUNT(DISTINCT cnpj_fundo) AS total_fundos
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY tp_fundo
ORDER BY pl_medio DESC;
```

**P5 — Captação positiva com SELIC acima de 10%**
```sql
SELECT tp_fundo,
       COUNT(DISTINCT cnpj_fundo) AS fundos_com_captacao_positiva,
       AVG(captacao_liquida_acumulada) AS captacao_media
FROM gold_cvm.fundo_mensal
WHERE taxa_anual_bcb > 10
  AND captacao_liquida_acumulada > 0
GROUP BY tp_fundo
ORDER BY captacao_media DESC;
```

---

## 5. YAGNI — O que foi removido e por quê

| Removido | Motivo |
|---|---|
| Prompt de tratamento de erro ("SQL falhou, tente reformular") | Responsabilidade do AGENT_CORE — o grafo LangGraph decide se retenta após `SQL_ERROR:` |
| Prompt de clarificação de ambiguidade | AGENT_CORE decide quando pedir clarificação ao usuário |
| Versões multilíngue (EN/PT) | 100% português brasileiro — sem alternativas no v1 |
| Prompt de sumário de conversa / memória | Fora do escopo v1; AGENT_CORE não tem memória persistente |
| Configuração de temperatura/max_tokens no prompt | Responsabilidade do AGENT_CORE ao instanciar o LLM |
| Few-shot com todas as 5 queries | P1 + P3 cobrem os dois schemas; P2, P4, P5 ficam como referência de domínio |
| Prompt de fallback para queries inválidas | Coberto pela resposta do agente quando `SqlExecuteTool` retorna `SQL_ERROR:` |

---

## 6. Rascunho de Requisitos para /define

### Funcionais
- [ ] Criar `prompts/sql_prompt.py` com `get_sql_prompt() -> ChatPromptTemplate` — few-shot (P1 + P3), variáveis `{schema}` e `{question}`
- [ ] Criar `prompts/interpretation_prompt.py` com `get_interpretation_prompt() -> ChatPromptTemplate` — variáveis `{question}`, `{sql}`, `{result}`
- [ ] Exportar ambas as funções via `prompts/__init__.py`
- [ ] SQL prompt instrui explicitamente: retornar apenas SQL puro — sem blocos ```sql```, sem comentários, sem texto adicional
- [ ] SQL prompt inclui regras de domínio: filtro outliers, limitação alpha_selic 2024-12, fundo_diario indisponível, LIMIT padrão

### Não-funcionais
- [ ] Ambos os templates são instâncias de `ChatPromptTemplate` (LangChain 0.3+)
- [ ] Funções factory (`get_sql_prompt`, `get_interpretation_prompt`) retornam instâncias prontas para uso com `.format_messages()` ou pipe LangChain
- [ ] Testes unitários: verificar variáveis esperadas e substrings críticas nos prompts formatados
- [ ] Sem dependências novas — apenas `langchain-core` (já presente)

---

## 7. Próximo Passo

```bash
/define .claude/sdd/features/BRAINSTORM_PROMPTS.md
```
