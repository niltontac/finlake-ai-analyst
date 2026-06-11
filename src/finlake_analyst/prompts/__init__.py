"""Templates de prompt Text-to-SQL e interpretação financeira brasileira."""

from finlake_analyst.prompts.interpretation_prompt import get_interpretation_prompt
from finlake_analyst.prompts.sql_prompt import get_sql_prompt

__all__ = ["get_sql_prompt", "get_interpretation_prompt"]
