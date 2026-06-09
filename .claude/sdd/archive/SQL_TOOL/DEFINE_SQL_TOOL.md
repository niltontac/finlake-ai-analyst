# DEFINE: SQL_TOOL

> Duas LangChain tools que conectam o agente LangGraph ao PostgreSQL Gold — `execute_sql` e `get_schema`.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | SQL_TOOL |
| **Data** | 2026-06-09 |
| **Autor** | Nilton Coura |
| **Status** | ✅ Shipped |
| **Clarity Score** | 14/15 |

---

## Problem Statement

O agente LangGraph não tem como executar SQL nem consultar o schema do banco de dados Gold. Sem essa camada, o modelo não consegue responder perguntas financeiras — ele sabe gerar SQL mas não tem ferramenta para executá-lo no PostgreSQL `:5433`. A SQL_TOOL preenche essa lacuna expondo duas tools bem definidas que o agente usa no padrão ReAct.

---

## Target Users

| Usuário | Papel | Pain Point |
|---|---|---|
| Nilton Coura | Desenvolvedor / dono do projeto | Precisa de tools testáveis e integráveis ao LangGraph |
| Agente LangGraph | Consumidor das tools | Precisa de interface clara para consultar schema e executar SQL com feedback de erro |

---

## Goals

| Prioridade | Goal |
|---|---|
| **MUST** | Criar `SqlExecuteTool(BaseTool)` que executa SELECT e retorna markdown table ou erro prefixado |
| **MUST** | Criar `SqlSchemaTool(BaseTool)` que retorna schema DDL + amostras + notas de qualidade dos dados |
| **MUST** | Criar `get_database()` singleton com `SQLDatabase` apontando para as 3 tabelas Gold expostas |
| **MUST** | Validar SELECT-only em `SqlExecuteTool` — rejeitar DDL/DML com `SECURITY_ERROR:` |
| **MUST** | Retornar erros PostgreSQL como string `SQL_ERROR: <mensagem>` (não levantar exceção) |
| **MUST** | Exportar ambas as tools via `tools/__init__.py` para consumo pelo `agent/` |
| **SHOULD** | `description` de cada tool em português, otimizados para o contexto financeiro brasileiro |
| **SHOULD** | Testes unitários com mock do `SQLDatabase` para `execute_sql` e `get_schema` |
| **COULD** | `max_rows` configurável via `Settings` (v1 fixa em 50) |

---

## Success Criteria

- [ ] `SqlExecuteTool._run("SELECT 1")` retorna string não-vazia sem levantar exceção
- [ ] `SqlExecuteTool._run("DELETE FROM gold_cvm.fundo_mensal")` retorna string iniciada com `"SECURITY_ERROR:"` sem executar nenhuma query no banco
- [ ] `SqlExecuteTool._run("SELECT * FROM tabela_que_nao_existe")` retorna string iniciada com `"SQL_ERROR:"` sem levantar exceção
- [ ] `SqlSchemaTool._run("")` retorna schema das 3 tabelas expostas (`macro_mensal`, `macro_diario`, `fundo_mensal`)
- [ ] Output de `SqlSchemaTool._run("")` contém ao menos uma das notas de qualidade documentadas (gestor, outliers, alpha_selic)
- [ ] `ruff check src/` zero violations nos arquivos novos
- [ ] `pytest tests/test_sql_execute.py tests/test_sql_schema.py` passa — mocks não conectam ao banco real

---

## Acceptance Tests

| ID | Cenário | Given | When | Then |
|---|---|---|---|---|
| AT-001 | SELECT válido retorna dados | Mock `SQLDatabase.run()` retorna string markdown | `SqlExecuteTool._run("SELECT date, taxa_anual FROM gold_bcb.macro_mensal LIMIT 3")` | Retorna string com `\|` (markdown table) sem exceção |
| AT-002 | SELECT retorna 0 linhas | Mock retorna string vazia | `SqlExecuteTool._run("SELECT 1 WHERE 1=0")` | Retorna string (pode ser vazia ou "0 rows") sem exceção |
| AT-003 | Non-SELECT rejeitado | Qualquer estado | `SqlExecuteTool._run("DELETE FROM gold_cvm.fundo_mensal")` | Retorna `"SECURITY_ERROR: Only SELECT queries are allowed"` sem chamar SQLDatabase |
| AT-004 | UPDATE rejeitado | Qualquer estado | `SqlExecuteTool._run("UPDATE gold_bcb.macro_mensal SET taxa_anual=0")` | Retorna `"SECURITY_ERROR: ..."` sem chamar SQLDatabase |
| AT-005 | Erro SQL retornado como string | Mock `SQLDatabase.run()` levanta `Exception("column x does not exist")` | `SqlExecuteTool._run("SELECT coluna_inexistente FROM gold_bcb.macro_mensal")` | Retorna `"SQL_ERROR: column x does not exist"` sem propagar exceção |
| AT-006 | Schema todas as tabelas | Mock `SQLDatabase.get_table_info()` retorna schema fixture | `SqlSchemaTool._run("")` | Retorna string contendo `macro_mensal`, `macro_diario`, `fundo_mensal` |
| AT-007 | Schema inclui notas de qualidade | Mock retorna schema fixture | `SqlSchemaTool._run("")` | Output contém substring `"gestor"` ou `"alpha_selic"` ou `"outlier"` |
| AT-008 | Query P5 do grounding | Mock retorna resultado fixture | `SqlExecuteTool._run(<query P5>)` | Retorna string sem exceção (valida que query passa na validação SELECT) |

---

## Out of Scope

- Retry automático dentro das tools (o agente LangGraph faz o retry via ReAct)
- Cache de resultados SQL
- `sql_db_query_checker` (chamada LLM extra, latência desnecessária)
- `sql_db_list_tables` como tool separada (coberto por `get_schema` sem parâmetro)
- Paginação de resultados (fixo em `max_rows=50`)
- `gold_cvm.fundo_diario` como tabela exposta (coberta por `fundo_mensal`)
- Usuário PostgreSQL read-only (documentado como melhoria de produção, não implementado em v1)
- Múltiplas conexões de banco (apenas PostgreSQL Gold `:5433`)

---

## Constraints

| Tipo | Constraint | Impacto |
|---|---|---|
| Técnico | Python 3.12, type hints obrigatórios, docstrings | Todos os arquivos novos seguem as convenções do finlake-brasil |
| Técnico | `langchain-community>=0.3` já em `pyproject.toml` | Usar `SQLDatabase` de `langchain_community.utilities` |
| Técnico | `DATABASE_URL` via `Settings` (não hardcoded) | `get_database()` lê de `get_settings().database_url` |
| Técnico | `src/` layout | Novos arquivos em `src/finlake_analyst/tools/` |
| Técnico | Testes com mock (não conexão real) | AT-001 a AT-008 não requerem PostgreSQL rodando |
| Segurança | SELECT-only validado no código | Produção deve usar usuário DB read-only (nota no CLAUDE.md) |

---

## Technical Context

| Aspecto | Valor | Notas |
|---|---|---|
| **Deployment Location** | `src/finlake_analyst/tools/` | `sql_execute.py`, `sql_schema.py`, `database.py` |
| **KB Domains** | `ai-data-engineering/llmops-patterns`, `python/clean-architecture` | Padrões de tools LangChain e arquitetura limpa Python |
| **IaC Impact** | None | PostgreSQL já existe em `:5433`; sem nova infraestrutura |

---

## Data Contract

### Tabelas expostas (via `include_tables`)

| Tabela | Schema | Colunas-chave | Notas |
|---|---|---|---|
| `macro_mensal` | `gold_bcb` | `date`, `taxa_anual`, `selic_real`, `ptax_media`, `acumulado_12m` | Dados macroeconômicos mensais BCB |
| `macro_diario` | `gold_bcb` | `date`, `taxa_anual`, `taxa_cambio`, `selic_real`, `variacao_diaria_pct` | Granularidade diária para queries pontuais |
| `fundo_mensal` | `gold_cvm` | `cnpj_fundo`, `ano_mes`, `tp_fundo`, `rentabilidade_mes_pct`, `alpha_selic`, `alpha_ipca`, `captacao_liquida_acumulada`, `taxa_anual_bcb` | Tabela principal; join BCB já aplicado |

### Notas de qualidade (incluídas no output de `SqlSchemaTool`)

- `gestor` é nulo na maioria dos registros de `fundo_mensal` — limitação da fonte CVM
- Outliers em `rentabilidade_mes_pct` (valores > 1000%) — erros de cadastro CVM; filtrar em queries de ranking
- `alpha_selic` e `alpha_ipca` disponíveis até 2024-12 — registros 2025/2026 existem mas sem cross-domain BCB
- `gold_cvm.fundo_diario` não exposta — usar `fundo_mensal` para análises conversacionais

### Queries de referência validadas

5 queries validadas pelo domínio disponíveis em `BRAINSTORM_SQL_TOOL.md` — usadas como fixtures de teste e benchmark de acurácia.

---

## Assumptions

| ID | Suposição | Se Errada, Impacto | Validado? |
|---|---|---|---|
| A-001 | `langchain_community.utilities.SQLDatabase` suporta `include_tables` com schema qualificado (`gold_bcb.macro_mensal`) | `get_database()` falharia; precisaria de workaround com schema_translate_map | [ ] |
| A-002 | `SQLDatabase.run()` levanta `Exception` (não retorna string de erro) em queries inválidas | AT-005 falharia; precisaria de `try/except` diferente | [ ] |
| A-003 | `SQLDatabase.get_table_info()` retorna DDL suficiente para o LLM gerar SQL correto | Agente geraria SQL com colunas erradas; precisaria de schema customizado | [ ] |
| A-004 | PostgreSQL `:5433` está acessível durante testes de integração | Testes unitários com mock não são afetados; testes de integração bloqueados | [ ] |

> **Nota sobre A-001:** LangChain `SQLDatabase` usa o schema padrão da conexão. Tabelas de schemas distintos (`gold_bcb`, `gold_cvm`) podem exigir configuração via `schema` param ou `search_path`. Validar no início do Build.

---

## Clarity Score Breakdown

| Elemento | Score (0-3) | Notas |
|---|---|---|
| Problem | 3 | Específico: agente sem interface SQL não responde perguntas |
| Users | 2 | Nilton (dev) + agente LangGraph como consumidor — único persona humano |
| Goals | 3 | 9 goals MoSCoW, interface das tools definida com inputs/outputs |
| Success | 3 | 7 critérios testáveis com strings de erro específicas (`SQL_ERROR:`, `SECURITY_ERROR:`) |
| Scope | 3 | 8 itens fora de escopo + 3 tabelas expostas explicitamente |
| **Total** | **14/15** | Passa o gate (12/15) |

---

## Open Questions

- **A-001** — `SQLDatabase` e schemas qualificados: verificar suporte a `include_tables=["gold_bcb.macro_mensal", ...]` vs. necessidade de `schema` param no início do Build.

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-09 | Nilton Coura | Versão inicial gerada a partir de BRAINSTORM_SQL_TOOL.md |
| 1.1 | 2026-06-09 | ship-agent | Shipped and archived |

---

## Next Step

**Pronto para:** `/design .claude/sdd/features/DEFINE_SQL_TOOL.md`
