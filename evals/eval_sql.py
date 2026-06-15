"""Script standalone de avaliação da qualidade SQL do agente FinLake Analyst.

Executa as 5 queries de referência (P1–P5) contra o agente e avalia a equivalência
semântica do SQL gerado com GEval (LLM-as-judge) do DeepEval 4.x.

Uso:
    uv run python evals/eval_sql.py

Pré-requisitos:
    ANTHROPIC_API_KEY e FINLAKE_DATABASE_URL configurados no .env.
    O banco PostgreSQL :5433 deve estar acessível.
"""

import asyncio
import logging
import sys

from deepeval.metrics import GEval
from deepeval.models.llms.anthropic_model import AnthropicModel
from deepeval.test_case import LLMTestCase, SingleTurnParams
from langgraph.graph.state import CompiledStateGraph

from finlake_analyst.agent import create_agent_graph
from finlake_analyst.agent.state import AgentState
from finlake_analyst.config import get_settings
from finlake_analyst.prompts import get_sql_prompt
from finlake_analyst.tools.sql_schema import SqlSchemaTool

_log = logging.getLogger(__name__)

# ─── Ground Truth P1–P5 ──────────────────────────────────────────────────────

_EXPECTED_P1 = """\
SELECT cnpj_fundo, gestor, ano_mes, rentabilidade_mes_pct, alpha_selic
FROM gold_cvm.fundo_mensal
WHERE alpha_selic > 0
  AND rentabilidade_mes_pct < 1000
  AND ano_mes >= '2024-10-01'
ORDER BY alpha_selic DESC
LIMIT 20"""

_EXPECTED_P2 = """\
SELECT cnpj_fundo, gestor, tp_fundo,
       SUM(captacao_liquida_acumulada) AS captacao_total
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY cnpj_fundo, gestor, tp_fundo
ORDER BY captacao_total DESC
LIMIT 10"""

_EXPECTED_P3 = """\
SELECT date, taxa_anual, selic_real, ptax_media
FROM gold_bcb.macro_mensal
WHERE date >= current_date - interval '12 months'
ORDER BY date ASC"""

_EXPECTED_P4 = """\
SELECT tp_fundo,
       AVG(vl_patrim_liq_medio) AS pl_medio,
       COUNT(DISTINCT cnpj_fundo) AS total_fundos
FROM gold_cvm.fundo_mensal
WHERE ano_mes BETWEEN '2024-01-01' AND '2024-12-01'
GROUP BY tp_fundo
ORDER BY pl_medio DESC"""

_EXPECTED_P5 = """\
SELECT tp_fundo,
       COUNT(DISTINCT cnpj_fundo) AS fundos_com_captacao_positiva,
       AVG(captacao_liquida_acumulada) AS captacao_media
FROM gold_cvm.fundo_mensal
WHERE taxa_anual_bcb > 10
  AND captacao_liquida_acumulada > 0
GROUP BY tp_fundo
ORDER BY captacao_media DESC"""

_TEST_CASES: list[dict[str, str]] = [
    {
        "id": "P1",
        "question": "Quais fundos com maior alpha_selic no último trimestre de 2024?",
        "expected_sql": _EXPECTED_P1,
    },
    {
        "id": "P2",
        "question": "Quais fundos tiveram maior captação líquida em 2024?",
        "expected_sql": _EXPECTED_P2,
    },
    {
        "id": "P3",
        "question": "Como evoluiu a SELIC real nos últimos 12 meses?",
        "expected_sql": _EXPECTED_P3,
    },
    {
        "id": "P4",
        "question": "Qual o patrimônio líquido médio por tipo de fundo em 2024?",
        "expected_sql": _EXPECTED_P4,
    },
    {
        "id": "P5",
        "question": "Quais tipos de fundo tiveram captação positiva com SELIC acima de 10%?",
        "expected_sql": _EXPECTED_P5,
    },
]

_GEVAL_CRITERIA = (
    "O SQL gerado responde à pergunta do usuário de forma semanticamente "
    "equivalente ao SQL esperado, considerando o schema disponível. "
    "Variações de formatação, aliases e ordem de cláusulas são aceitáveis "
    "desde que o resultado da query seja equivalente."
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _build_metric(model: AnthropicModel) -> GEval:
    """Cria métrica GEval para equivalência semântica SQL."""
    return GEval(
        name="SQL Correctness",
        criteria=_GEVAL_CRITERIA,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        model=model,
        threshold=0.7,
    )


async def _generate_sql(graph: CompiledStateGraph, question: str) -> str:
    """Executa o grafo para uma pergunta e retorna o SQL gerado."""
    state: AgentState = {
        "question": question,
        "sql": "",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }
    result = await graph.ainvoke(state)
    return result.get("sql", "")


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    """Executa evals P1–P5 e imprime resultados com score por query."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

    settings = get_settings()
    schema = SqlSchemaTool()._run("")
    sql_prompt = get_sql_prompt().partial(schema=schema)
    graph = create_agent_graph(sql_prompt)

    anthropic_model = AnthropicModel(
        model=settings.model_name,
        api_key=settings.anthropic_api_key,
    )
    metric = _build_metric(anthropic_model)

    print("\n=== FinLake Analyst — SQL Eval (P1–P5) ===\n")

    passed = 0
    for tc in _TEST_CASES:
        _log.info("Gerando SQL para %s", tc["id"])
        actual_sql = await _generate_sql(graph, tc["question"])

        test_case = LLMTestCase(
            input=tc["question"],
            actual_output=actual_sql,
            expected_output=tc["expected_sql"],
        )
        metric.measure(test_case)

        score = metric.score if metric.score is not None else 0.0
        status = "✓ PASS" if metric.is_successful() else "✗ FAIL"
        reason_short = (metric.reason or "")[:120]
        print(f"  {tc['id']}: {status}  score={score:.2f}  — {reason_short}")

        if metric.is_successful():
            passed += 1

    overall = passed / len(_TEST_CASES)
    print(f"\nScore geral: {passed}/{len(_TEST_CASES)}  ({overall:.0%})")

    if passed < len(_TEST_CASES):
        print("\nQueries com score < 0.7:")
        for tc in _TEST_CASES:
            print(f"  {tc['id']}: {tc['question']}")

    sys.exit(0 if passed >= 3 else 1)


if __name__ == "__main__":
    asyncio.run(main())
