# BRAINSTORM: SQL_TOOL

**Projeto:** finlake-ai-analyst  
**Data:** 2026-06-09  
**Status:** Concluído — pronto para `/define`  
**Fase:** 0 de 5 (Brainstorm)

---

## 1. Contexto

A feature **SQL_TOOL** é a ponte entre o agente LangGraph e os dados Gold do PostgreSQL. Ela implementa as duas tools que o agente usará no padrão ReAct para responder perguntas financeiras em português:

1. **`execute_sql`** — recebe SQL gerado pelo LLM, valida que é SELECT, executa e retorna resultado ou erro
2. **`get_schema`** — retorna schema DDL + amostras das tabelas Gold para o agente construir SQL correto

A fundação (INFRA_BASE) já está operacional: `config.py` tem `DATABASE_URL`, `tools/` existe como sub-package.

---

## 2. Decisões Tomadas

### Q1 — Escopo: quantas tools?
**Decisão: duas tools (`execute_sql` + `get_schema`)**  
Motivo: padrão ReAct Text-to-SQL — o agente consulta o schema antes de gerar SQL, aumentando a acurácia. O toolkit completo do LangChain (4 tools) adiciona `query_checker` (chamada LLM extra) e `list_tables` (redundante com `get_schema`).

### Q2 — Segurança SQL
**Decisão: validação no código (`SELECT`-only) + nota de produção**  
Motivo: v1 de portfólio — validação no código é pragmática. A recomendação de usar usuário PostgreSQL read-only em produção fica documentada no CLAUDE.md. Defesa em profundidade é mencionada como melhoria futura.

### Q3 — Tratamento de erro
**Decisão: retornar erro como resultado da tool (`"SQL_ERROR: <mensagem>"`)**  
Motivo: padrão ReAct — o agente LangGraph recebe o erro PostgreSQL e pode autocorrigir o SQL na próxima iteração. Retry interno na tool esconderia falhas do LangFuse.

### Q4 — Formato do resultado
**Decisão: markdown table**  
Motivo: LangChain `SQLDatabase` retorna nesse formato nativamente. Legível para o LLM gerar respostas em português sem pós-processamento adicional.

### Q5 — Tabelas expostas ao agente
**Decisão: 3 tabelas via `include_tables`**

| Tabela | Inclusa | Motivo |
|---|---|---|
| `gold_bcb.macro_mensal` | Sim | Dados macroeconômicos mensais (SELIC, PTAX, IPCA) |
| `gold_bcb.macro_diario` | Sim | Granularidade diária quando relevante (ex: PTAX de uma data específica) |
| `gold_cvm.fundo_mensal` | Sim | Tabela principal — rentabilidade, captação, alpha pré-calculados |
| `gold_cvm.fundo_diario` | Não | Tabela grande; informação coberta por `fundo_mensal` para análises conversacionais |

**`max_rows=50`** — suficiente para queries analíticas conversacionais.

---

## 3. Abordagem Selecionada

### Abordagem A: Custom tools sobre `SQLDatabase` ⭐ Selecionada

Criar dois `BaseTool` customizados usando `langchain_community.utilities.SQLDatabase` como backend:

```
tools/
├── __init__.py
├── sql_execute.py   # SqlExecuteTool(BaseTool)
└── sql_schema.py    # SqlSchemaTool(BaseTool)
```

**`execute_sql`**
- Input: `query: str` — SQL gerado pelo LLM
- Validação: rejeita qualquer query que não comece com `SELECT` (case-insensitive, strip whitespace)
- Execução: via `SQLDatabase.run(query)`
- Output (sucesso): markdown table com até `max_rows=50` linhas
- Output (erro SQL): `"SQL_ERROR: <mensagem PostgreSQL>"` — o agente pode tentar corrigir
- Output (violação SELECT): `"SECURITY_ERROR: Only SELECT queries are allowed"`

**`get_schema`**
- Input: `table_names: list[str]` — tabelas solicitadas (default: todas as 3 expostas)
- Output: schema DDL-like + 3 linhas de amostra por tabela (via `SQLDatabase.get_table_info`)
- Inclui nota de qualidade dos dados como parte do output (ver seção 4)

**Alternativas rejeitadas:**
- **`SQLDatabaseToolkit` completo** — sem validação SELECT nativa, `query_checker` adiciona latência desnecessária
- **SQLAlchemy direto** — reimplementa o que `SQLDatabase` já oferece (connection pooling, `get_table_info`, row formatting)

---

## 4. Amostras para Grounding

### Queries validadas pelo domínio

**P1 — Alpha SELIC recente**
```sql
SELECT cnpj_fundo, gestor, ano_mes, rentabilidade_mes_pct, alpha_selic
FROM gold_cvm.fundo_mensal
WHERE alpha_selic > 0
  AND rentabilidade_mes_pct < 1000
  AND ano_mes >= '2024-10-01'
ORDER BY alpha_selic DESC
LIMIT 20;
```

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

**P3 — Comportamento da SELIC (12 meses)**
```sql
SELECT date, taxa_anual, selic_real, ptax_media
FROM gold_bcb.macro_mensal
WHERE date >= current_date - interval '12 months'
ORDER BY date ASC;
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

### Notas de qualidade dos dados (incluídas no output de `get_schema`)

- **`gestor` é nulo na maioria dos registros** — limitação da fonte CVM; não usar como filtro primário
- **Outliers em `rentabilidade_mes_pct`** — valores > 1000% existem (erros de cadastro CVM); filtrar com `rentabilidade_mes_pct < 1000` em queries de ranking
- **`alpha_selic` calculado disponível até 2024-12** — registros de 2025/2026 existem em `fundo_mensal` mas sem `alpha_selic`/`alpha_ipca` calculados (cross-domain BCB pendente)
- **`fundo_diario` não disponível** — análises diárias de fundos não são suportadas nesta versão; usar `fundo_mensal` para análises de captação e rentabilidade

---

## 5. YAGNI — O que foi removido e por quê

| Removido | Motivo |
|---|---|
| Retry interno na tool | O agente LangGraph faz o retry via ReAct — retry na tool esconde falhas |
| Cache de resultados | LangFuse rastreia traces; cache é complexidade sem benefício claro no v1 |
| `sql_db_query_checker` | Chamada LLM extra por query — latência + custo sem ganho mensurável |
| `sql_db_list_tables` | `get_schema` sem parâmetro já lista as tabelas disponíveis |
| Paginação de resultados | `max_rows=50` fixo — queries analíticas conversacionais raramente precisam de mais |
| `gold_cvm.fundo_diario` | Tabela grande; `fundo_mensal` cobre os casos de uso conversacionais |
| `gold_bcb.macro_diario` como tabela primária | Inclusa, mas queries de análise tendem ao mensal — diário disponível para casos específicos |
| Usuário read-only no banco (v1) | YAGNI para portfólio; documentado como melhoria de produção |

---

## 6. Rascunho de Requisitos para /define

### Funcionais
- [ ] Criar `tools/sql_execute.py` com `SqlExecuteTool(BaseTool)` — valida SELECT, executa, retorna markdown ou erro
- [ ] Criar `tools/sql_schema.py` com `SqlSchemaTool(BaseTool)` — retorna schema + amostras + notas de qualidade
- [ ] Criar `tools/database.py` com `get_database()` — singleton `SQLDatabase` conectado a `DATABASE_URL` com `include_tables` das 3 tabelas Gold
- [ ] Exportar ambas as tools via `tools/__init__.py` para consumo pelo `agent/`
- [ ] Validação SELECT em `SqlExecuteTool`: rejeitar queries que não começam com `SELECT` (após strip e upper)
- [ ] `max_rows=50` configurado no `SQLDatabase`

### Não-funcionais
- [ ] Ambas as tools têm `name` e `description` em português, otimizados para o contexto financeiro
- [ ] Erros PostgreSQL retornados como string prefixada com `"SQL_ERROR:"` (não como exceção)
- [ ] Violações de segurança retornadas como `"SECURITY_ERROR:"` (não como exceção)
- [ ] Notas de qualidade dos dados embutidas no output de `get_schema`
- [ ] Testes: `test_sql_execute.py` e `test_sql_schema.py` com mock do `SQLDatabase`

---

## 7. Próximo Passo

```bash
/define .claude/sdd/features/BRAINSTORM_SQL_TOOL.md
```
