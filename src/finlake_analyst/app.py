"""Entry point Chainlit do finlake-analyst.

Executar com:
    uv run chainlit run src/finlake_analyst/app.py --watch
"""

import chainlit as cl

from finlake_analyst.agent import create_agent_graph
from finlake_analyst.agent.state import AgentState
from finlake_analyst.config import get_settings
from finlake_analyst.prompts import get_sql_prompt
from finlake_analyst.tools.sql_schema import SqlSchemaTool

_settings = get_settings()


@cl.on_chat_start
async def on_chat_start() -> None:
    """Inicializa sessão — injeta schema, compila grafo e armazena na sessão."""
    schema = SqlSchemaTool()._run("")
    sql_prompt = get_sql_prompt().partial(schema=schema)
    graph = create_agent_graph(sql_prompt)
    cl.user_session.set("graph", graph)
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
    """Processa pergunta do usuário via grafo LangGraph com streaming."""
    graph = cl.user_session.get("graph")

    initial_state: AgentState = {
        "question": message.content,
        "sql": "",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }

    msg = cl.Message(content="")
    error_fallback = ""

    async for event in graph.astream_events(initial_state, version="v2"):
        kind = event["event"]
        node = event["metadata"].get("langgraph_node", "")

        if kind == "on_chat_model_stream" and node == "interpret_result":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                await msg.stream_token(chunk.content)

        elif kind == "on_chain_end" and event.get("name") == "handle_error":
            output = event["data"].get("output", {})
            if isinstance(output, dict):
                error_fallback = output.get("analysis", "")

    if not msg.content and error_fallback:
        msg.content = error_fallback

    await msg.send()
