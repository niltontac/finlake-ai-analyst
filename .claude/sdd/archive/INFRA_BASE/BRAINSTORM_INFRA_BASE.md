# BRAINSTORM: INFRA_BASE

**Projeto:** finlake-ai-analyst  
**Data:** 2026-06-08  
**Status:** Concluído — pronto para `/define`  
**Fase:** 0 de 5 (Brainstorm)

---

## 1. Contexto do Projeto

O `finlake-ai-analyst` é a camada de AI Engineering do **FinLake Brasil** — plataforma de dados financeiros brasileiros com Medallion Architecture (Bronze→Silver→Gold) e Data Mesh em 2 domínios:

- **BCB**: SELIC, IPCA, PTAX (Banco Central do Brasil)
- **CVM**: Fundos de investimento (Comissão de Valores Mobiliários)

### Problema que resolve

O usuário hoje precisa abrir o Metabase, saber qual dashboard olhar e interpretar os dados manualmente. Este projeto resolve a **última milha**: o usuário faz uma pergunta em português e recebe uma resposta direta com os dados do Gold, sem escrever SQL, sem abrir dashboard.

**Exemplo de pergunta real:**
> "Quais fundos multimercado tiveram captação líquida positiva nos últimos 3 meses com SELIC acima de 10%?"

### Escopo v1
- Text-to-SQL interativo sobre `gold_bcb` e `gold_cvm`
- Interpretação financeira do resultado (não só dado bruto)
- Monitoramento on-demand via pergunta natural

### Fora do escopo v1
- Alertas proativos (v2, via Airflow)
- RAG sobre documentos CVM (stretch goal)

---

## 2. Fonte de Dados (Grounding)

Os dados Gold já existem no **PostgreSQL 15 na porta :5433** do projeto `finlake-brasil`.

### Schemas relevantes

**`gold_bcb.macro_diario`**
| Coluna | Tipo | Descrição |
|---|---|---|
| date | date | Data de referência |
| taxa_anual | numeric(8,4) | SELIC anual |
| taxa_cambio | numeric(10,4) | PTAX |
| variacao_diaria_pct | numeric(8,4) | Variação diária |
| acumulado_12m | numeric(8,4) | Acumulado 12 meses |
| selic_real | numeric(8,4) | SELIC descontado IPCA |
| transformed_at | timestamptz | Timestamp de transformação |

**`gold_bcb.macro_mensal`**
| Coluna | Tipo | Descrição |
|---|---|---|
| date | date | Mês de referência |
| taxa_anual | numeric(8,4) | SELIC anual |
| acumulado_12m | numeric(8,4) | Acumulado 12 meses |
| selic_real | numeric(8,4) | SELIC real |
| ptax_media | numeric(8,4) | PTAX média mensal |
| ptax_variacao_mensal_pct | numeric(8,4) | Variação mensal PTAX |

**`gold_cvm.fundo_diario`**
| Coluna | Tipo | Descrição |
|---|---|---|
| cnpj_fundo | varchar(18) | Identificador do fundo |
| dt_comptc | date | Data de competência |
| tp_fundo | varchar(50) | Tipo do fundo |
| vl_quota / vl_quota_anterior | numeric(22,8) | Valor da cota |
| vl_patrim_liq | numeric(22,6) | Patrimônio líquido |
| captacao_liquida | numeric(22,6) | Captação líquida diária |
| rentabilidade_diaria_pct | numeric | Rentabilidade diária |

**`gold_cvm.fundo_mensal`** ⭐ Tabela principal para análises
| Coluna | Tipo | Descrição |
|---|---|---|
| cnpj_fundo | varchar(18) | Identificador do fundo |
| ano_mes | date | Mês de referência |
| tp_fundo / gestor | text | Tipo e gestor |
| rentabilidade_mes_pct | numeric | Rentabilidade mensal |
| captacao_liquida_acumulada | numeric(22,6) | Captação acumulada no mês |
| vl_patrim_liq_medio | numeric(22,6) | PL médio mensal |
| nr_cotst_medio | numeric(10,2) | Número médio de cotistas |
| taxa_anual_bcb | numeric(8,4) | SELIC do período (cross-domain) |
| acumulado_12m_ipca | numeric(8,4) | IPCA do período (cross-domain) |
| alpha_selic | numeric | Rentabilidade acima da SELIC |
| alpha_ipca | numeric | Rentabilidade acima do IPCA |

> **Nota:** `gold_cvm.fundo_mensal` já tem `alpha_selic` e `alpha_ipca` calculados — os joins cross-domain BCB↔CVM já foram feitos na camada Gold. O agente pode responder perguntas de performance relativa diretamente sem joins complexos.

---

## 3. Decisões Tomadas

### Q1 — Gerenciador de dependências
**Decisão: `uv`**  
Motivo: Padrão do KB, mais rápido, lockfile nativo, consistente com as convenções do `finlake-brasil`. O `.venv/` existente será descartado e reiniciado com `uv init`.

### Q2 — Docker Compose
**Decisão: Nenhum Docker Compose na INFRA_BASE**  
Motivo: PostgreSQL Gold já roda no `finlake-brasil` em `:5433`. LangFuse via cloud (`langfuse.com`) — sem infra local necessária. O agente roda com `uv run chainlit run`.

### Q3 — Layout do projeto
**Decisão: `src/` layout** → `src/finlake_analyst/`  
Motivo: Padrão profissional recomendado pelo Python Packaging Guide. Evita imports acidentais. Demonstra senioridade no portfólio.

### Q4 — Modelo LLM
**Decisão: Anthropic Claude `claude-sonnet-4-6` como padrão, configurável via `.env`**  
Motivo: Excelente raciocínio em SQL complexo e contexto longo. Consistência com o ambiente de desenvolvimento (Claude Code). `MODEL_NAME` no `.env` permite trocar para evals comparativos com DeepEval.

### Q5 — LangFuse
**Decisão: LangFuse Cloud (`langfuse.com`)**  
Motivo: Sem overhead de infraestrutura local. Adequado para v1 e portfólio.

---

## 4. Abordagem Selecionada

### Estrutura do projeto

```
finlake-ai-analyst/
├── src/
│   └── finlake_analyst/
│       ├── __init__.py
│       ├── config.py          # pydantic-settings, lê .env
│       ├── app.py             # entry point Chainlit
│       ├── agent/             # grafo LangGraph
│       │   └── __init__.py
│       ├── tools/             # LangChain tools (SQL query, schema inspector)
│       │   └── __init__.py
│       └── prompts/           # templates de prompt (Text-to-SQL, interpretação)
│           └── __init__.py
├── tests/
│   └── __init__.py
├── .claude/
│   └── sdd/
│       └── features/
│           └── BRAINSTORM_INFRA_BASE.md  (este arquivo)
├── .env.example
├── .gitignore
├── CLAUDE.md
└── pyproject.toml
```

### `pyproject.toml`

```toml
[project]
name = "finlake-analyst"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langchain>=0.3",
    "langchain-anthropic>=0.3",
    "langchain-community>=0.3",   # SQLDatabase toolkit
    "langgraph>=0.2",
    "langfuse>=2.0",
    "chainlit>=1.3",
    "psycopg2-binary>=2.9",       # driver PostgreSQL
    "sqlalchemy>=2.0",             # abstração SQL para LangChain
    "pydantic-settings>=2.0",     # config.py via .env
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "deepeval>=1.4",              # evals de qualidade (dev/CI only)
]
```

> **Decisão:** `deepeval` movido para `dev` — só é necessário em pipelines de avaliação de qualidade, não em runtime de produção.

### `.env.example`

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
MODEL_NAME=claude-sonnet-4-6

# PostgreSQL Gold (finlake-brasil :5433)
DATABASE_URL=postgresql://user:password@localhost:5433/finlake

# LangFuse Cloud (langfuse.com)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Chainlit
CHAINLIT_AUTH_SECRET=your-secret-here
```

---

## 5. YAGNI — O que foi removido e por quê

| Removido | Motivo |
|---|---|
| Docker Compose | LangFuse cloud + DB no projeto pai eliminam necessidade |
| `database/` como módulo separado | V1 tem 2-3 funções de DB — cabe dentro de `tools/` |
| CI/CD (`.github/workflows/`) | Escopo de feature separada, não INFRA_BASE |
| `evals/` estruturado | DeepEval entra na feature de qualidade (futura) |
| `docs/diagrams/` | Gerado após design, não em infra |
| `deepeval` em runtime | Só necessário em avaliações, movido para `dev` |

---

## 6. Convenções herdadas do finlake-brasil

- Python 3.12 com type hints obrigatórios
- Docstrings em todos os módulos, classes e funções públicas
- Variáveis de ambiente para todas as credenciais (nunca hardcoded)
- Commits em inglês, conventional commits
- Gerenciamento de pacotes: `uv`
- Método: SDD via AgentSpec (brainstorm → define → design → build → ship)
- Specs documentadas em `.claude/sdd/features/`

---

## 7. Rascunho de Requisitos para /define

### Funcionais
- [ ] Inicializar projeto com `uv init` e `pyproject.toml` configurado
- [ ] Criar estrutura `src/finlake_analyst/` com módulos vazios (agent, tools, prompts)
- [ ] Criar `config.py` com `pydantic-settings` lendo todas as variáveis do `.env.example`
- [ ] Criar `.env.example` com todas as variáveis necessárias documentadas
- [ ] Criar `app.py` como entry point Chainlit (placeholder funcional)
- [ ] Criar `CLAUDE.md` do projeto com stack, convenções e como rodar
- [ ] Criar `.gitignore` adequado (Python + uv + .env)
- [ ] Criar `tests/__init__.py` para preparar estrutura de testes

### Não-funcionais
- [ ] `uv lock` commitado no repositório (lockfile determinístico)
- [ ] Nenhuma credencial hardcoded em nenhum arquivo
- [ ] `ruff` configurado no `pyproject.toml` (linter + formatter)
- [ ] `.env` no `.gitignore` (apenas `.env.example` commitado)

---

## 8. Próximo Passo

```bash
/define .claude/sdd/features/BRAINSTORM_INFRA_BASE.md
```
