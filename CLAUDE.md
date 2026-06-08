# finlake-ai-analyst

Camada de AI Engineering do FinLake Brasil — agente Text-to-SQL que responde
perguntas financeiras em português sobre dados Gold do PostgreSQL.

## Stack

| Componente | Tecnologia | Propósito |
|---|---|---|
| Orquestração | LangGraph | Grafo stateful do agente |
| Tooling | LangChain | SQLDatabase toolkit |
| Interface | Chainlit | Chat conversacional |
| Observabilidade | LangFuse Cloud | Traces e métricas |
| Evals | DeepEval | Qualidade das respostas |
| Dados | PostgreSQL :5433 | Gold schemas (finlake-brasil) |
| LLM | Anthropic Claude | Geração SQL + interpretação financeira |

## Como executar

```bash
# 1. Instalar dependências
uv sync
uv sync --group dev

# 2. Configurar ambiente
cp .env.example .env
# Edite .env com suas credenciais

# 3. Rodar o agente
uv run chainlit run src/finlake_analyst/app.py --watch

# 4. Executar testes
uv run pytest tests/ -v

# 5. Lint
uv run ruff check src/
```

## Schemas Gold disponíveis

O banco PostgreSQL roda em `:5433` no projeto `finlake-brasil`.

**gold_bcb** — Banco Central do Brasil
- `macro_diario`: SELIC diária, PTAX, variações, selic_real
- `macro_mensal`: SELIC, PTAX, IPCA acumulados mensais

**gold_cvm** — Comissão de Valores Mobiliários
- `fundo_diario`: cotas, captação e rentabilidade diária por fundo (CNPJ)
- `fundo_mensal`: rentabilidade mensal, `alpha_selic`, `alpha_ipca` — joins BCB já aplicados na camada Gold

## Estrutura do projeto

```
src/finlake_analyst/
├── config.py       # pydantic-settings — fonte de verdade de configuração
├── app.py          # entry point Chainlit
├── agent/          # grafo LangGraph (feature AGENT_CORE)
├── tools/          # LangChain tools — SQL executor, schema inspector (feature SQL_TOOL)
└── prompts/        # templates Text-to-SQL e interpretação (feature PROMPTS)
```

## Convenções

- Python 3.12, type hints obrigatórios, docstrings em módulos/classes/funções públicas
- PEP 8 + ruff (line-length=100)
- Commits em inglês, conventional commits
- Credenciais sempre via `.env`, nunca hardcoded
- Método de desenvolvimento: SDD via AgentSpec (brainstorm → define → design → build → ship)
- Specs em `.claude/sdd/features/`

## Features (SDD)

| Feature | Status | Spec |
|---|---|---|
| INFRA_BASE | Done | [DESIGN_INFRA_BASE.md](.claude/sdd/features/DESIGN_INFRA_BASE.md) |
| AGENT_CORE | Planned | — |
| SQL_TOOL | Planned | — |
| PROMPTS | Planned | — |
| OBSERVABILITY | Planned | — |

## Decisões arquiteturais

Ver ADRs inline em `.claude/sdd/features/DESIGN_INFRA_BASE.md` — seção "Key Decisions".
