# DEFINE: INFRA_BASE

> Fundação do projeto finlake-ai-analyst — estrutura, dependências e configuração base para o agente Text-to-SQL financeiro.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | INFRA_BASE |
| **Data** | 2026-06-08 |
| **Autor** | Nilton Coura |
| **Status** | Shipped |
| **Clarity Score** | 13/15 |

---

## Problem Statement

O repositório `finlake-ai-analyst` está vazio — sem estrutura de código, sem dependências e sem configuração de ambiente. Para que qualquer feature do agente Text-to-SQL possa ser desenvolvida, é necessário estabelecer uma fundação padronizada, reproduzível e alinhada com as convenções do projeto pai `finlake-brasil`, eliminando dívida técnica desde o início.

---

## Target Users

| Usuário | Papel | Pain Point |
|---|---|---|
| Nilton Coura | Desenvolvedor / dono do projeto | Iniciar desenvolvimento sem estrutura leva a inconsistências e retrabalho |
| Futuras features (agent, tools, prompts) | Consumidores da infra | Precisam de config, entry point e módulos esqueleto já disponíveis |

---

## Goals

O que o sucesso parece (priorizado):

| Prioridade | Goal |
|---|---|
| **MUST** | Inicializar projeto com `uv` e `pyproject.toml` com todas as dependências pinadas |
| **MUST** | Criar estrutura `src/finlake_analyst/` com módulos esqueleto (agent, tools, prompts) |
| **MUST** | Criar `config.py` com `pydantic-settings` lendo todas as variáveis do `.env.example` |
| **MUST** | Criar `.env.example` documentado com todas as variáveis necessárias |
| **MUST** | Criar `CLAUDE.md` do projeto com stack, convenções e como executar |
| **MUST** | Criar `.gitignore` adequado (Python + uv + .env) |
| **SHOULD** | Criar `tests/__init__.py` preparando estrutura para futuros testes |
| **SHOULD** | Configurar `ruff` no `pyproject.toml` (linter + formatter) |
| **COULD** | Criar `app.py` placeholder funcional para o Chainlit (entrada para o agente) |

**Guia de prioridade:**
- **MUST** = MVP falha sem isso
- **SHOULD** = Importante, mas existe workaround
- **COULD** = Nice-to-have, cortar primeiro se necessário

---

## Success Criteria

Critérios mensuráveis — todos devem passar antes de fechar a feature:

- [ ] `uv sync` completa sem erros com o `pyproject.toml` gerado
- [ ] `uv sync --group dev` instala dependências de desenvolvimento (incluindo `deepeval`, `pytest`, `ruff`)
- [ ] `python -c "from finlake_analyst.config import Settings; Settings()"` carrega configuração sem erro quando `.env` está presente e válido
- [ ] `python -c "from finlake_analyst.config import Settings; Settings()"` levanta `ValidationError` com mensagem clara quando variáveis obrigatórias estão ausentes
- [ ] `ruff check src/` retorna zero violations nos arquivos gerados
- [ ] `uv.lock` está presente e commitado no repositório
- [ ] Nenhum arquivo commitado contém credencial hardcoded (`.env` não commitado, apenas `.env.example`)

---

## Acceptance Tests

| ID | Cenário | Given | When | Then |
|---|---|---|---|---|
| AT-001 | Setup feliz | `.env` válido com todas as variáveis, `uv sync` executado | `python -c "from finlake_analyst.config import Settings; s = Settings(); print(s.model_name)"` | Imprime `claude-sonnet-4-6` (ou valor do `.env`) sem erro |
| AT-002 | Variável ausente | `.env` sem `ANTHROPIC_API_KEY` | `from finlake_analyst.config import Settings; Settings()` | `ValidationError` com mensagem indicando qual campo está faltando |
| AT-003 | Dev dependencies | `uv sync --group dev` executado | `pytest tests/ -v` | `0 failed`, `tests/__init__.py` reconhecido |
| AT-004 | Linting limpo | Todos os arquivos Python gerados | `ruff check src/` | Saída vazia (zero violations) |
| AT-005 | Sem segredos | `.env` criado localmente | `git status` + `git diff --cached` | `.env` aparece em `.gitignore`, não em staged files |
| AT-006 | Imports funcionam | `uv sync` executado | `python -c "from finlake_analyst import agent, tools, prompts"` | Import sem erro (módulos existem mesmo que vazios) |

---

## Out of Scope

Explicitamente **não incluso** nesta feature:

- Implementação do grafo LangGraph (feature `AGENT_CORE`)
- LangChain tools para SQL execution (feature `SQL_TOOL`)
- Prompt templates de Text-to-SQL (feature `PROMPTS`)
- Integração LangFuse (feature `OBSERVABILITY`)
- Interface Chainlit funcional (feature `UI`)
- Testes de integração com PostgreSQL :5433 (feature `AGENT_CORE`)
- Docker Compose (decisão YAGNI — LangFuse cloud, DB externo)
- CI/CD pipeline (feature separada)
- `evals/` estruturado para DeepEval (feature de qualidade)
- RAG sobre documentos CVM (v2)
- Alertas proativos via Airflow (v2)

---

## Constraints

| Tipo | Constraint | Impacto |
|---|---|---|
| Técnico | Python 3.12 (convenção finlake-brasil) | `requires-python = ">=3.12"` no pyproject.toml |
| Técnico | `uv` como gerenciador de dependências | Sem `requirements.txt`, sem `poetry.lock` — apenas `uv.lock` |
| Técnico | PostgreSQL :5433 já existente no finlake-brasil | Config deve aceitar `DATABASE_URL` via `.env`, não criar DB |
| Técnico | LangFuse via cloud (langfuse.com) | Sem Docker Compose para LangFuse |
| Técnico | `src/` layout | `src/finlake_analyst/` — não `analyst/` na raiz |
| Portfólio | Demonstrar senioridade Staff Engineer | CLAUDE.md deve explicar *por que* as decisões foram tomadas, não só *o quê* |

---

## Technical Context

> Contexto essencial para a fase de Design.

| Aspecto | Valor | Notas |
|---|---|---|
| **Deployment Location** | Raiz do repositório + `src/finlake_analyst/` | `src/` layout — padrão Python Packaging Guide |
| **KB Domains** | `python/clean-architecture`, `ai-data-engineering/llmops-patterns` | Padrões de estrutura de projeto e LLMOps |
| **IaC Impact** | None | DB existente em `:5433`, LangFuse cloud — sem nova infra |

**Por que isso importa:**
- **Location** → Design usa `src/finlake_analyst/` como raiz de todos os módulos
- **KB Domains** → Design consulta padrões de `config.py` com pydantic-settings e projeto Python moderno
- **IaC Impact** → Nenhuma mudança de infraestrutura nesta feature

---

## Data Contract

> N/A para INFRA_BASE — esta feature não processa dados, apenas estabelece a fundação do projeto.

A integração com os schemas `gold_bcb` e `gold_cvm` será coberta nas features `SQL_TOOL` e `AGENT_CORE`, que consumirão `config.py` e a conexão PostgreSQL definida aqui via `DATABASE_URL`.

---

## Assumptions

Suposições que, se erradas, invalidam o design:

| ID | Suposição | Se Errada, Impacto | Validado? |
|---|---|---|---|
| A-001 | `uv` está instalado no ambiente de desenvolvimento | `uv init` falha — precisaria de fallback para pip/poetry | [ ] |
| A-002 | PostgreSQL :5433 do finlake-brasil está acessível localmente | AT-001 e testes de integração futuros falham | [ ] |
| A-003 | Credenciais Anthropic (`ANTHROPIC_API_KEY`) disponíveis para desenvolvimento | AT-001 falha — precisaria de mock no teste | [ ] |
| A-004 | Credenciais LangFuse cloud disponíveis | LangFuse não rastreia traces — feature de observabilidade bloqueada | [ ] |
| A-005 | Python 3.12 disponível via `uv` (auto-instalado ou via pyenv) | `uv sync` falha com versão incorreta | [ ] |

**Nota:** Validar A-001 e A-005 antes do Design. A-002, A-003, A-004 podem ser validados no início do Build.

---

## Clarity Score Breakdown

| Elemento | Score (0-3) | Notas |
|---|---|---|
| Problem | 3 | Específico: repositório vazio, convenções definidas, contexto claro |
| Users | 2 | Nilton identificado com pain point, mas único persona — portfólio solo |
| Goals | 3 | MoSCoW explícito com 9 goals priorizados |
| Success | 2 | Critérios definidos via comandos executáveis; sem métricas de performance (N/A para infra) |
| Scope | 3 | In/out scope explícitos, YAGNI documentado, 10 itens fora de escopo listados |
| **Total** | **13/15** | Passa o gate mínimo (12/15) |

---

## Open Questions

Nenhuma — pronto para Design.

> A-001 e A-005 das Assumptions devem ser verificadas no início do Build (não bloqueiam o Design).

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-08 | Nilton Coura | Versão inicial gerada a partir de BRAINSTORM_INFRA_BASE.md |

---

## Next Step

**Pronto para:** `/design .claude/sdd/features/DEFINE_INFRA_BASE.md`
