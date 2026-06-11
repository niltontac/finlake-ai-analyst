"""Testes estruturais dos templates de prompt — sem banco de dados ou API."""

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
    assert "sem blocos" in messages[0].content


def test_interpretation_prompt_references_financial_context() -> None:
    """Interpretation prompt referencia contexto financeiro brasileiro."""
    messages = get_interpretation_prompt().format_messages(
        question="q", sql="SELECT 1", result="r"
    )
    system_content = messages[0].content
    assert any(kw in system_content for kw in ["SELIC", "CDI", "benchmark"])
