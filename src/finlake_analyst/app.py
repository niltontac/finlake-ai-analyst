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
