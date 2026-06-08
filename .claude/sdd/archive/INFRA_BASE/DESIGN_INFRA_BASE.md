# DESIGN: INFRA_BASE

> Fundação técnica do finlake-ai-analyst — scaffold de projeto, dependências, configuração e módulos esqueleto para o agente Text-to-SQL financeiro.

## Metadata

| Atributo | Valor |
|---|---|
| **Feature** | INFRA_BASE |
| **Data** | 2026-06-08 |
| **Autor** | Nilton Coura |
| **DEFINE** | [DEFINE_INFRA_BASE.md](./DEFINE_INFRA_BASE.md) |
| **Status** | Shipped |

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                      finlake-ai-analyst                              │
│                                                                      │
│   .env ────────────────────────────────────────────────────┐        │
│   (nunca commitado)                                        │        │
│                                                            ▼        │
│   pyproject.toml                              config.py (Settings)  │
│   uv.lock                                           │               │
│   (dependências pinadas)                            │               │
│                                     ┌───────────────┼───────────┐   │
│                                     ▼               ▼           ▼   │
│                               agent/          tools/       prompts/ │
│                               (skeleton)      (skeleton)   (skeleton)│
│                                     │               │           │   │
│                                     └───────────────┴───────────┘   │
│                                                     │               │
│                                                     ▼               │
│                                                   app.py            │
│                                             (Chainlit entry)        │
│                                                     │               │
│                                    ┌────────────────┴────────────┐  │
│                                    ▼                             ▼  │
│                        PostgreSQL :5433               LangFuse Cloud│
│                        (finlake-brasil)               (langfuse.com)│
│                        gold_bcb / gold_cvm                          │
│                                                                      │
│   ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ FUTURE ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│   agent/ ← LangGraph stateful graph              (feature AGENT_CORE)│
│   tools/ ← LangChain SQLDatabase toolkit          (feature SQL_TOOL) │
│   prompts/ ← Text-to-SQL templates               (feature PROMPTS)  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Components

| Componente | Propósito | Tecnologia |
|---|---|---|
| `pyproject.toml` | Manifesto do pacote, dependências, ferramentas | uv + hatchling |
| `uv.lock` | Lockfile determinístico | uv |
| `config.py` | Carregamento e validação de variáveis de ambiente | pydantic-settings |
| `app.py` | Entry point da interface conversacional | Chainlit |
| `agent/` | Sub-package do grafo LangGraph (skeleton v1) | LangGraph |
| `tools/` | Sub-package das LangChain tools (skeleton v1) | LangChain |
| `prompts/` | Sub-package dos templates de prompt (skeleton v1) | LangChain PromptTemplate |
| `tests/` | Pacote de testes | pytest |
| `.env.example` | Template documentado de variáveis de ambiente | — |
| `.gitignore` | Exclusões de VCS | — |
| `CLAUDE.md` | Documentação do projeto para Claude Code | — |

---

## Key Decisions

### Decisão 1: `uv` como único gerenciador de dependências

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-08 |

**Contexto:** O projeto precisa de um gerenciador de dependências Python moderno que gere um lockfile determinístico, seja rápido e alinhado com o `finlake-brasil`.

**Escolha:** `uv` com `pyproject.toml` e `uv.lock` commitado.

**Rationale:** `uv` substitui pip, virtualenv e pyenv em um único binário. É 10-100x mais rápido que pip, gera lockfile nativo (`uv.lock`), e é o padrão do projeto pai. O `.venv` existente no repositório será removido e recriado via `uv sync`.

**Alternativas rejeitadas:**
1. **Poetry** — overhead maior, `poetry.lock` formato proprietário, substituído pelo `uv` na comunidade Python moderna
2. **pip + requirements.txt** — sem lockfile real (`requirements.txt` não é lockfile), sem gestão de versão do Python

**Consequências:**
- Desenvolvedores precisam ter `uv` instalado (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- `uv.lock` commitado garante reprodutibilidade entre ambientes

---

### Decisão 2: `src/` layout

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-08 |

**Contexto:** Onde colocar o código Python do pacote `finlake_analyst`.

**Escolha:** `src/finlake_analyst/` — Python Packaging Guide src layout.

**Rationale:** O `src/` layout isola o código instalável do código de projeto (tests, scripts, docs). Evita que `import finlake_analyst` funcione sem instalação prévia, o que mascara erros de empacotamento. Demonstra conhecimento de boas práticas para portfólio Staff Engineer.

**Alternativas rejeitadas:**
1. **Flat layout** (`analyst/` na raiz) — `import analyst` funcionaria sem instalação, escondendo problemas de packaging; menos profissional para portfólio
2. **Monorepo com múltiplos pacotes** — YAGNI para v1 solo

**Consequências:**
- `uv sync` (com `pip install -e .`) é necessário antes de `import finlake_analyst`
- `pyproject.toml` precisa de `[tool.hatch.build.targets.wheel] packages = ["src/finlake_analyst"]`

---

### Decisão 3: `pydantic-settings` para gerenciamento de configuração

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-08 |

**Contexto:** O projeto tem 7 variáveis de ambiente obrigatórias de 4 sistemas distintos (Anthropic, PostgreSQL, LangFuse, Chainlit). Precisamos de carregamento tipado com validação.

**Escolha:** `pydantic-settings` com classe `Settings(BaseSettings)`.

**Rationale:** Carregamento automático de `.env`, validação com `Field(...)` para campos obrigatórios, type hints nativos, `ValidationError` com mensagem clara quando campo está ausente. Compatível com o ecossistema LangChain/FastAPI (LangChain internamente usa pydantic). Um único objeto `Settings()` é a fonte de verdade de toda a configuração.

**Alternativas rejeitadas:**
1. **`python-dotenv` sozinho** — carrega strings brutas sem validação, sem type safety
2. **`os.environ` direto** — verboso, sem validação, sem documentação automática dos campos

**Consequências:**
- `Settings()` levanta `ValidationError` na inicialização se qualquer campo obrigatório estiver ausente — fail-fast desejável
- `model_config = SettingsConfigDict(env_file=".env")` permite sobrescrever via variáveis de ambiente reais (CI/CD)

---

### Decisão 4: Módulos como sub-packages separados desde o início

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-08 |

**Contexto:** Como estruturar internamente `src/finlake_analyst/` para as features futuras.

**Escolha:** `agent/`, `tools/`, `prompts/` como sub-packages com `__init__.py` (skeletons na v1).

**Rationale:** Cada pasta mapeia 1:1 para um conceito do LangGraph pipeline: o grafo (`agent/`), as ferramentas LangChain (`tools/`), e os templates de prompt (`prompts/`). Separação de responsabilidades desde o início evita refactor na feature AGENT_CORE. Fácil de explicar no README como decisão arquitetural intencional.

**Alternativas rejeitadas:**
1. **Arquivos únicos** (`agent.py`, `tools.py`) — escalam mal; quando `tools.py` tiver `SQLTool`, `SchemaInspector`, `QueryExecutor`, a divisão em módulos será necessária de qualquer forma
2. **`database/` como módulo separado** — YAGNI; na v1 o acesso ao DB cabe em 2-3 funções dentro de `tools/`

**Consequências:**
- Features futuras têm um lugar definido para cada novo componente
- Build phase pode trabalhar em `agent/`, `tools/`, `prompts/` em paralelo sem conflito

---

### Decisão 5: LangFuse via cloud, sem Docker Compose

| Atributo | Valor |
|---|---|
| **Status** | Accepted |
| **Data** | 2026-06-08 |

**Contexto:** LangFuse self-hosted requer PostgreSQL próprio + servidor, adicionando Docker Compose ao projeto.

**Escolha:** `langfuse.com` cloud com credentials via `.env`.

**Rationale:** Sem overhead de infraestrutura local. O banco de dados Gold já está no `finlake-brasil` em `:5433`. Adicionar Docker Compose na INFRA_BASE adicionaria complexidade desnecessária. Para portfólio, langfuse.com cloud tem tier gratuito suficiente.

**Alternativas rejeitadas:**
1. **LangFuse self-hosted** — Compose com `postgres:langfuse` + `langfuse/langfuse` containers. Adequado para produção enterprise, YAGNI para v1 portfólio.
2. **Sem observabilidade** — Sacrifica rastreabilidade dos traces desde o início. LangFuse cloud é gratuito e vale a complexidade mínima (só variáveis de ambiente).

**Consequências:**
- 3 variáveis de ambiente adicionais no `.env.example` (PUBLIC_KEY, SECRET_KEY, HOST)
- Integração real do LangFuse SDK implementada na feature OBSERVABILITY, não aqui

---

## File Manifest

| # | Arquivo | Ação | Propósito | Dependências |
|---|---|---|---|---|
| 1 | `pyproject.toml` | Create | Manifesto do pacote, dependências, ruff, pytest config | — |
| 2 | `.env.example` | Create | Template documentado de variáveis de ambiente | — |
| 3 | `.gitignore` | Create | Excluir .env, .venv, __pycache__, .ruff_cache, uv cache | — |
| 4 | `CLAUDE.md` | Create | Documentação do projeto para Claude Code | — |
| 5 | `src/finlake_analyst/__init__.py` | Create | Package root com version string | — |
| 6 | `src/finlake_analyst/config.py` | Create | Settings via pydantic-settings, fonte de verdade de config | 2 |
| 7 | `src/finlake_analyst/app.py` | Create | Chainlit entry point placeholder | 5, 6 |
| 8 | `src/finlake_analyst/agent/__init__.py` | Create | Agent sub-package skeleton | 5 |
| 9 | `src/finlake_analyst/tools/__init__.py` | Create | Tools sub-package skeleton | 5 |
| 10 | `src/finlake_analyst/prompts/__init__.py` | Create | Prompts sub-package skeleton | 5 |
| 11 | `tests/__init__.py` | Create | Test package root | — |
| 12 | `tests/test_config.py` | Create | Testa Settings carregamento e ValidationError | 6 |

**Total de arquivos:** 12

**Comando para gerar lockfile após criar #1:**
```bash
uv sync
uv sync --group dev
```

---

## Agent Assignment Rationale

| Agente | Arquivos | Motivo |
|---|---|---|
| @python-developer | 1, 5, 6, 7, 8, 9, 10, 11, 12 | Código Python com dataclasses, type hints, pydantic-settings |
| @ai-prompt-specialist | — (v2) | Prompts implementados em feature PROMPTS |
| (general) | 2, 3, 4 | Arquivos de configuração/texto sem especialização necessária |

---

## Code Patterns

### Pattern 1: `config.py` — Settings com pydantic-settings

```python
# src/finlake_analyst/config.py
"""Configuração centralizada do finlake-analyst via variáveis de ambiente."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração da aplicação — carregada do .env na inicialização."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    model_name: str = Field(default="claude-sonnet-4-6", description="LLM model name")

    # PostgreSQL Gold (finlake-brasil :5433)
    database_url: str = Field(
        ...,
        description="PostgreSQL connection URL — aponta para finlake-brasil :5433",
    )

    # LangFuse Cloud
    langfuse_public_key: str = Field(..., description="LangFuse public key (pk-lf-...)")
    langfuse_secret_key: str = Field(..., description="LangFuse secret key (sk-lf-...)")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        description="LangFuse host",
    )

    # Chainlit
    chainlit_auth_secret: str = Field(..., description="Chainlit auth secret")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância singleton de Settings (cached)."""
    return Settings()
```

> **Por que `lru_cache`:** `Settings()` lê o `.env` a cada instanciação. O cache garante que o arquivo seja lido uma única vez por processo. A função `get_settings()` é o ponto de injeção para testes — `monkeypatch` pode sobrescrever via `get_settings.cache_clear()`.

---

### Pattern 2: `app.py` — Chainlit entry point placeholder

```python
# src/finlake_analyst/app.py
"""Entry point Chainlit do finlake-analyst.

Executar com:
    uv run chainlit run src/finlake_analyst/app.py --watch
"""
import chainlit as cl

from finlake_analyst.config import get_settings

_settings = get_settings()


@cl.on_chat_start
async def on_chat_start() -> None:
    """Inicializa sessão de chat."""
    await cl.Message(
        content=(
            "Olá! Sou o **FinLake Analyst**, seu assistente para análise de "
            "dados financeiros brasileiros.\n\n"
            "Faça uma pergunta sobre fundos de investimento ou indicadores "
            "macroeconômicos (SELIC, IPCA, PTAX).\n\n"
            f"_Modelo: {_settings.model_name}_"
        ),
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Processa mensagem do usuário — placeholder para feature AGENT_CORE."""
    await cl.Message(
        content=(
            f"Pergunta recebida: **{message.content}**\n\n"
            "O agente Text-to-SQL está em construção (feature AGENT_CORE). "
            "A infraestrutura base está operacional."
        ),
    ).send()
```

---

### Pattern 3: `pyproject.toml` completo

```toml
[project]
name = "finlake-analyst"
version = "0.1.0"
description = "AI analyst layer for FinLake Brasil — Text-to-SQL over financial Gold data"
readme = "README.md"
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
    "pydantic-settings>=2.0",     # configuração via .env
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
    "deepeval>=1.4",              # evals de qualidade (dev/CI only)
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/finlake_analyst"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "ANN"]
ignore = ["ANN101", "ANN102"]

[tool.ruff.lint.isort]
known-first-party = ["finlake_analyst"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

### Pattern 4: `tests/test_config.py` — testes de Settings

```python
# tests/test_config.py
"""Testes de carregamento e validação de configuração."""
import pytest
from pydantic import ValidationError

from finlake_analyst.config import Settings, get_settings

_VALID_ENV: dict[str, str] = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "DATABASE_URL": "postgresql://user:pass@localhost:5433/finlake",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
    "LANGFUSE_SECRET_KEY": "sk-lf-test",
    "CHAINLIT_AUTH_SECRET": "test-secret",
}


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """Limpa cache de Settings entre testes."""
    get_settings.cache_clear()


def test_settings_loads_with_valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings carrega corretamente com todas as variáveis definidas."""
    for key, value in _VALID_ENV.items():
        monkeypatch.setenv(key, value)

    settings = Settings()

    assert settings.model_name == "claude-sonnet-4-6"
    assert settings.langfuse_host == "https://cloud.langfuse.com"
    assert settings.anthropic_api_key == "sk-ant-test"


def test_settings_missing_required_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """ValidationError com campo identificado quando variável obrigatória ausente."""
    for key, value in _VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert "anthropic_api_key" in str(exc_info.value).lower()


def test_model_name_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    """MODEL_NAME pode ser sobrescrito via variável de ambiente."""
    for key, value in _VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MODEL_NAME", "claude-opus-4-8")

    settings = Settings()

    assert settings.model_name == "claude-opus-4-8"
```

---

### Pattern 5: `__init__.py` dos sub-packages (esqueleto)

```python
# src/finlake_analyst/__init__.py
"""finlake-analyst — AI analyst layer for FinLake Brasil."""

__version__ = "0.1.0"
```

```python
# src/finlake_analyst/agent/__init__.py
"""Módulo do agente LangGraph — implementado na feature AGENT_CORE."""
```

```python
# src/finlake_analyst/tools/__init__.py
"""LangChain tools para execução SQL — implementadas na feature SQL_TOOL."""
```

```python
# src/finlake_analyst/prompts/__init__.py
"""Templates de prompt Text-to-SQL — implementados na feature PROMPTS."""
```

---

### Pattern 6: `.env.example`

```bash
# =============================================================================
# finlake-analyst — variáveis de ambiente
# Copie para .env e preencha os valores reais.
# NUNCA commite o .env. Apenas .env.example é versionado.
# =============================================================================

# -----------------------------------------------------------------------------
# Anthropic — modelo LLM
# Obtenha em: https://console.anthropic.com
# -----------------------------------------------------------------------------
ANTHROPIC_API_KEY=sk-ant-...
MODEL_NAME=claude-sonnet-4-6

# -----------------------------------------------------------------------------
# PostgreSQL Gold — finlake-brasil :5433
# Schemas disponíveis: gold_bcb, gold_cvm
# -----------------------------------------------------------------------------
DATABASE_URL=postgresql://user:password@localhost:5433/finlake

# -----------------------------------------------------------------------------
# LangFuse Cloud — observabilidade de traces
# Crie conta gratuita em: https://cloud.langfuse.com
# -----------------------------------------------------------------------------
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com

# -----------------------------------------------------------------------------
# Chainlit — interface conversacional
# Gere com: python -c "import secrets; print(secrets.token_hex(32))"
# -----------------------------------------------------------------------------
CHAINLIT_AUTH_SECRET=your-secret-here
```

---

### Pattern 7: `.gitignore`

```gitignore
# Ambiente e segredos
.env
.env.local
.env.*.local

# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg
*.egg-info/
dist/
build/
*.spec

# uv
.venv/
uv.cache/

# Ruff
.ruff_cache/

# pytest
.pytest_cache/
htmlcov/
.coverage
coverage.xml

# IDEs
.idea/
.vscode/
*.swp
*.swo
.DS_Store

# Chainlit
.chainlit/
chainlit.md

# LangFuse local (se self-hosted futuramente)
langfuse-data/
```

---

### Pattern 8: `CLAUDE.md`

```markdown
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
| LLM | Anthropic Claude | Geração SQL + interpretação |

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

**gold_bcb** — Banco Central do Brasil
- `macro_diario`: SELIC diária, PTAX, variações
- `macro_mensal`: SELIC, PTAX, IPCA acumulados mensais

**gold_cvm** — Comissão de Valores Mobiliários
- `fundo_diario`: cotas e captação diária por fundo
- `fundo_mensal`: rentabilidade, alpha_selic, alpha_ipca mensais (já com joins BCB)

## Convenções

- Python 3.12, type hints obrigatórios, docstrings em módulos/classes/funções públicas
- PEP 8 + ruff (line-length=100)
- Commits em inglês, conventional commits
- Credenciais sempre via .env, nunca hardcoded
- Método de desenvolvimento: SDD via AgentSpec

## Features (SDD)

| Feature | Status | Arquivo |
|---|---|---|
| INFRA_BASE | Building | DESIGN_INFRA_BASE.md |
| AGENT_CORE | Planned | — |
| SQL_TOOL | Planned | — |
| PROMPTS | Planned | — |
| OBSERVABILITY | Planned | — |
```

---

## Data Flow

```text
1. Usuário faz pergunta no Chainlit
   │
   ▼
2. app.py recebe cl.Message
   │
   ▼
3. [AGENT_CORE] LangGraph graph processa
   │
   ├──▶ [SQL_TOOL] LangChain SQLDatabase gera e executa SQL
   │         │
   │         ▼
   │    PostgreSQL :5433 (gold_bcb / gold_cvm)
   │         │
   │         ▼
   │    Resultado tabulado
   │
   ├──▶ [PROMPTS] Prompt de interpretação financeira
   │         │
   │         ▼
   │    Claude claude-sonnet-4-6 (Anthropic)
   │         │
   │         ▼
   │    Resposta em português com contexto financeiro
   │
   └──▶ [OBSERVABILITY] LangFuse trace (async)
              │
              ▼
         langfuse.com dashboard

4. Chainlit exibe resposta ao usuário
```

> **INFRA_BASE cobre:** steps 1, 2 (placeholder), e as credenciais de 3 e 4.
> Os steps de processamento real são implementados em features subsequentes.

---

## Integration Points

| Sistema Externo | Tipo | Autenticação | Configurado em |
|---|---|---|---|
| PostgreSQL :5433 (finlake-brasil) | SQLAlchemy + psycopg2 | `DATABASE_URL` via `.env` | `config.py` → `tools/` (AGENT_CORE) |
| Anthropic Claude API | `langchain-anthropic` SDK | `ANTHROPIC_API_KEY` via `.env` | `config.py` → `agent/` (AGENT_CORE) |
| LangFuse Cloud | `langfuse` Python SDK | `PUBLIC_KEY` + `SECRET_KEY` via `.env` | `config.py` → integração (OBSERVABILITY) |
| Chainlit | Framework web | `CHAINLIT_AUTH_SECRET` via `.env` | `app.py` |

---

## Testing Strategy

| Tipo | Escopo | Arquivo | Ferramentas | Meta |
|---|---|---|---|---|
| Unit | `config.py` Settings | `tests/test_config.py` | pytest + monkeypatch | Carregamento válido + ValidationError |
| Unit | Imports dos sub-packages | `tests/test_imports.py` (AGENT_CORE) | pytest | `from finlake_analyst import agent, tools, prompts` sem erro |
| Manual | `uv sync` + `uv run` | — | terminal | AT-001 a AT-006 do DEFINE |
| Manual | `.env` no `.gitignore` | — | `git status` | AT-005 do DEFINE |

**Cobertura mínima esperada na INFRA_BASE:** `config.py` coberto por 3 testes (`test_config.py`). Módulos skeleton têm cobertura zero — implementados em features futuras.

---

## Error Handling

| Erro | Estratégia | Retry? |
|---|---|---|
| `.env` ausente | `pydantic_settings` cai para variáveis de ambiente do sistema. Se também ausentes, `ValidationError` com campos faltantes. | Não — fix de config |
| Campo obrigatório ausente no `.env` | `ValidationError` na inicialização de `Settings()` — fail-fast | Não — fix de config |
| Importação de sub-package falha | `ImportError` explícito — indica problema de instalação (`uv sync` não foi rodado) | Não — fix de setup |
| `DATABASE_URL` inválida | Detectado em runtime na conexão — fora do escopo da INFRA_BASE | Não aplicável aqui |

---

## Configuration

| Key | Tipo | Default | Obrigatório | Descrição |
|---|---|---|---|---|
| `ANTHROPIC_API_KEY` | str | — | Sim | Chave de API Anthropic |
| `MODEL_NAME` | str | `claude-sonnet-4-6` | Não | Nome do modelo LLM |
| `DATABASE_URL` | str | — | Sim | PostgreSQL connection string |
| `LANGFUSE_PUBLIC_KEY` | str | — | Sim | LangFuse cloud public key |
| `LANGFUSE_SECRET_KEY` | str | — | Sim | LangFuse cloud secret key |
| `LANGFUSE_HOST` | str | `https://cloud.langfuse.com` | Não | LangFuse host |
| `CHAINLIT_AUTH_SECRET` | str | — | Sim | Chainlit authentication secret |

---

## Security Considerations

- `.env` explicitamente no `.gitignore` — única linha de defesa contra vazamento de credenciais
- `.env.example` com valores placeholder (`sk-ant-...`, `pk-lf-...`) — nunca valores reais
- `pydantic-settings` com `extra="ignore"` — variáveis desconhecidas ignoradas, sem runtime surpresas
- `CHAINLIT_AUTH_SECRET` obrigatório — sem autenticação default insegura
- `Field(...)` para todos os campos sensíveis — ausência detectada imediatamente na inicialização, antes de qualquer requisição chegar ao agente

---

## Observability

| Aspecto | Implementação na INFRA_BASE |
|---|---|
| Logging | Stdout padrão do Chainlit — nenhuma configuração adicional |
| Tracing | Credentials LangFuse configuradas no `.env` — SDK integrado na feature OBSERVABILITY |
| Métricas | N/A — INFRA_BASE não processa dados |

---

## Revision History

| Versão | Data | Autor | Alterações |
|---|---|---|---|
| 1.0 | 2026-06-08 | Nilton Coura | Versão inicial gerada a partir de DEFINE_INFRA_BASE.md |

---

## Next Step

**Pronto para:** `/build .claude/sdd/features/DESIGN_INFRA_BASE.md`
