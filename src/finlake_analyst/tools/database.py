"""Singleton SQLDatabase com acesso multi-schema ao PostgreSQL Gold."""

from functools import lru_cache

from langchain_community.utilities import SQLDatabase
from sqlalchemy import Engine, create_engine

from finlake_analyst.config import get_settings

_EXPOSED_TABLES: list[str] = ["macro_mensal", "macro_diario", "fundo_mensal"]


def _create_engine(database_url: str) -> Engine:
    """Cria engine SQLAlchemy com search_path para acesso multi-schema."""
    return create_engine(
        database_url,
        connect_args={"options": "-c search_path=gold_bcb,gold_cvm"},
    )


@lru_cache(maxsize=1)
def get_database() -> SQLDatabase:
    """Retorna instância singleton de SQLDatabase conectada ao Gold PostgreSQL."""
    settings = get_settings()
    engine = _create_engine(settings.finlake_database_url)
    return SQLDatabase(
        engine=engine,
        include_tables=_EXPOSED_TABLES,
        sample_rows_in_table_info=3,
    )
