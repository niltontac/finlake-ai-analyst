# FinLake AI Analyst

> Camada de AI Engineering sobre o [FinLake Brasil](https://github.com/niltontac/finlake-brasil) — agente conversacional que responde perguntas financeiras em português a partir dos dados Gold do BCB e CVM, sem escrever SQL, sem abrir dashboards.

---

## O Problema

Analistas e gestores que precisam de insights sobre fundos de investimento e indicadores macroeconômicos brasileiros enfrentam um fluxo manual e fragmentado: abrir e identificar o dashboard certo, interpretar os dados e cruzar informações de fontes distintas. O FinLake AI Analyst resolve a **última milha**: o usuário faz uma pergunta em português e recebe uma análise financeira contextualizada em segundos.

---

## Demonstração

### Análise de desempenho relativo (BCB × CVM)

> *"Quais tipos de fundo conseguiram superar a SELIC consistentemente em 2024, e qual foi o alpha médio?"*

![Análise de fundos que superaram a SELIC em 2024](docs/screenshots/demo-alpha-selic.png)

*O agente cruza os dados Gold de fundos CVM com os indicadores macroeconômicos BCB, identifica 4.002 fundos com alpha positivo e entrega análise com contexto de mercado — sem um único join escrito pelo usuário.*

---

### Análise temporal com correlação SELIC

> *"Como a captação líquida dos fundos de investimento evoluiu ao longo de 2024? Houve correlação com as mudanças na taxa SELIC?"*

![Análise de captação líquida e correlação com a SELIC em 2024](docs/screenshots/demo-captacao-temporal.png)

*O agente constrói uma narrativa temporal completa: de R$ 109,7 bilhões em captação em janeiro a -R$ 235 bilhões em resgates em dezembro, com explicação causal do comportamento dos investidores frente ao ciclo de alta da SELIC.*

---

### Análise crítica de dados

> *"Quais os 10 fundos com maior alpha acima da SELIC no último trimestre de 2024, e o que esses resultados significam para um investidor?"*

![Análise crítica identificando outliers e inconsistências na base CVM](docs/screenshots/demo-outliers-cvm.png)

*O agente não se limita a retornar o ranking — identifica retornos de 429% ao mês como outliers suspeitos, sinaliza inconsistências de dados da CVM e contextualiza o que um analista deve verificar antes de confiar nos números.*

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                  finlake-ai-analyst                      │
│                                                         │
│   Chainlit (interface conversacional)                   │
│         │                                               │
│         ▼                                               │
│   LangGraph StateGraph                                  │
│   ┌──────────────────────────────────┐                  │
│   │  generate_sql  →  execute_sql    │                  │
│   │       ↑               │          │                  │
│   │  retry (max 2)    sucesso        │                  │
│   │                       ▼          │                  │
│   │              interpret_result    │                  │
│   └──────────────────────────────────┘                  │
│         │                                               │
│         ▼                                               │
│   LangFuse Cloud (traces + métricas)                    │
└─────────────────────────────────────────────────────────┘
          │
          ▼ (DATABASE_URL)
┌─────────────────────────────────────────────────────────┐
│              finlake-brasil (PostgreSQL :5433)           │
│  gold_bcb.macro_mensal   │   gold_cvm.fundo_mensal      │
│  gold_bcb.macro_diario   │   (alpha_selic pré-calculado) │
└─────────────────────────────────────────────────────────┘
```

**Fluxo por pergunta:**
1. Usuário digita pergunta em português no Chainlit
2. `generate_sql` — Claude gera SQL PostgreSQL baseado no schema Gold
3. `execute_sql` — executa no banco, valida SELECT, retorna resultado
4. Se SQL falhou → retry com contexto do erro (máximo 2 tentativas)
5. `interpret_result` — Claude interpreta o resultado com contexto financeiro brasileiro
6. Resposta streamada token a token para o usuário

---

## Stack

| Componente | Tecnologia | Propósito |
|---|---|---|
| Orquestração | LangGraph 1.2 | Grafo stateful com retry automático |
| LLM | Claude Sonnet 4.6 (Anthropic) | Geração SQL + interpretação financeira |
| Tooling | LangChain + SQLDatabase | Execução SQL no PostgreSQL Gold |
| Interface | Chainlit 2.x | Chat conversacional com streaming |
| Observabilidade | LangFuse Cloud | Traces por pergunta, tokens, latência |
| Evals | DeepEval 4.x + GEval | Avaliação de qualidade SQL (LLM-as-judge) |
| Config | pydantic-settings | Gerenciamento de credenciais via `.env` |
| Dados | PostgreSQL 15 (:5433) | Schemas Gold do FinLake Brasil |

---

## Pré-requisitos

- Python 3.12
- [FinLake Brasil](https://github.com/niltontac/finlake-brasil) rodando com `make up` (PostgreSQL :5433 acessível)
- Conta Anthropic com créditos ([console.anthropic.com](https://console.anthropic.com))
- Conta LangFuse Cloud gratuita ([langfuse.com](https://langfuse.com))
- `uv` instalado ([astral.sh/uv](https://astral.sh/uv))

---

## Como rodar

```bash
# 1. Clonar e instalar
git clone https://github.com/niltontac/finlake-ai-analyst.git
cd finlake-ai-analyst
uv sync

# 2. Configurar credenciais
cp .env.example .env
# Editar .env com ANTHROPIC_API_KEY, FINLAKE_DATABASE_URL e chaves LangFuse

# 3. Garantir que o FinLake Brasil está rodando
cd ../finlake-brasil && make up

# 4. Subir o agente
cd ../finlake-ai-analyst
uv run chainlit run src/finlake_analyst/app.py --watch
# Acesse: http://localhost:8000
```

---

## Variáveis de ambiente

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
MODEL_NAME=claude-sonnet-4-6

# PostgreSQL Gold (finlake-brasil :5433)
FINLAKE_DATABASE_URL=postgresql://user:password@localhost:5433/finlake

# LangFuse Cloud (langfuse.com — free tier)
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://us.cloud.langfuse.com

# Chainlit
CHAINLIT_AUTH_SECRET=your-secret-here
```

---

## Estrutura do projeto

```
finlake-ai-analyst/
├── src/finlake_analyst/
│   ├── agent/
│   │   ├── state.py          # AgentState TypedDict
│   │   ├── nodes.py          # Factories dos nós LangGraph
│   │   └── graph.py          # StateGraph + routing condicional
│   ├── tools/
│   │   ├── database.py       # SQLDatabase singleton multi-schema
│   │   ├── sql_execute.py    # SqlExecuteTool — valida SELECT, executa
│   │   └── sql_schema.py     # SqlSchemaTool — DDL + notas de qualidade
│   ├── prompts/
│   │   ├── sql_prompt.py     # Few-shot Text-to-SQL em português
│   │   └── interpretation_prompt.py  # Analista financeiro sênior
│   ├── config.py             # pydantic-settings
│   └── app.py                # Chainlit entry point + LangFuse
├── evals/
│   └── eval_sql.py           # Script DeepEval P1–P5 (GEval SQL correctness)
├── tests/                    # 42 testes unitários
├── .env.example
└── pyproject.toml
```

---

## Decisões arquiteturais

**Por que repositório separado do FinLake Brasil?**
Em Data Mesh, o FinLake Brasil é o *data product* — produz e disponibiliza os dados Gold. O FinLake AI Analyst é um *data consumer* — consome via contrato de dados (PostgreSQL :5433, schemas `gold_bcb` e `gold_cvm`). São ciclos de deploy e responsabilidades distintos.

**Por que LangGraph em vez de `create_react_agent`?**
O agente precisa de dois LLM calls com prompts distintos (geração SQL + interpretação financeira) mais ciclo de retry controlado. O `create_react_agent` colapsaria os dois prompts num único call, perdendo a separação de responsabilidades e dificultando observabilidade nos traces.

**Por que dois prompts separados?**
`sql_prompt` instrui o modelo a gerar SQL puro sem markdown — com regras específicas do domínio financeiro brasileiro (filtrar outliers `rentabilidade_mes_pct < 1000`, `alpha_selic` disponível até 2024-12). `interpretation_prompt` instrui um analista financeiro sênior a contextualizar o resultado em termos de SELIC, CDI e alpha. Responsabilidades distintas, prompts distintos.

**Por que o agente não expõe o SQL ao usuário?**
O SQL é um detalhe de implementação. O streaming filtra por `langgraph_node == "interpret_result"` — apenas a análise financeira chega ao usuário.

---

## Evals de qualidade

Script de avaliação offline usando DeepEval + GEval (LLM-as-judge) com 5 queries de referência validadas contra o banco real:

```bash
uv run python evals/eval_sql.py
```

Avalia se o SQL gerado pelo agente é semanticamente equivalente ao SQL esperado — tolerando variações de formatação e aliases válidos.

---

## Testes

```bash
# Suite completa (42 testes unitários — sem banco ou API)
uv run pytest tests/ -v

# Lint
uv run ruff check src/ evals/
```

Os testes cobrem: routing do grafo (6 casos), nós individualmente com `AsyncMock` (13 casos), templates de prompt (8 casos), tools SQL (11 casos) e configuração (3 casos).

---

## Relação com o FinLake Brasil

Este projeto consome os dados Gold produzidos pelo [FinLake Brasil](https://github.com/niltontac/finlake-brasil) — plataforma de dados financeiros com Medallion Architecture (Bronze → Silver → Gold) e Data Mesh em 2 domínios: BCB (SELIC, IPCA, PTAX) e CVM (fundos de investimento).

O único ponto de integração é a conexão direta ao PostgreSQL :5433 — os schemas `gold_bcb` e `gold_cvm` são o contrato de dados entre os dois projetos. O campo `alpha_selic` em `gold_cvm.fundo_mensal` já traz o cruzamento BCB×CVM pré-calculado na camada Gold, simplificando as queries do agente.

---

## Autor

**Nilton Coura** — Senior Data Engineer

13 anos em tecnologia, 5 anos focados em Engenharia de Dados, atualmente especializado em AI Data Engineering — construindo plataformas de dados AI-ready com LLMs, agentes e pipelines inteligentes.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-niltontac-blue)](https://linkedin.com/in/niltontac)
[![GitHub](https://img.shields.io/badge/GitHub-niltontac-black)](https://github.com/niltontac)
[![FinLake Brasil](https://img.shields.io/badge/Projeto_Pai-finlake--brasil-green)](https://github.com/niltontac/finlake-brasil)
