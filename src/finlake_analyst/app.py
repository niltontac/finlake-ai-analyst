"""Entry point Chainlit do finlake-analyst.

Executar com:
    uv run chainlit run src/finlake_analyst/app.py --watch
"""

import logging
import os

import chainlit as cl

from finlake_analyst.agent import create_agent_graph
from finlake_analyst.agent.state import AgentState
from finlake_analyst.config import get_settings
from finlake_analyst.prompts import get_sql_prompt
from finlake_analyst.tools.sql_schema import SqlSchemaTool

_settings = get_settings()
_log = logging.getLogger(__name__)

# Bridges pydantic-settings → LangFuse 4.x env-var config.
# setdefault does not overwrite variables already present in the real environment.
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", _settings.langfuse_public_key)
os.environ.setdefault("LANGFUSE_SECRET_KEY", _settings.langfuse_secret_key)
os.environ.setdefault("LANGFUSE_HOST", _settings.langfuse_host)


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
    """Processa pergunta do usuário via grafo LangGraph com streaming e LangFuse traces."""
    graph = cl.user_session.get("graph")

    initial_state: AgentState = {
        "question": message.content,
        "sql": "",
        "sql_result": "",
        "retry_count": 0,
        "error": None,
        "analysis": "",
    }

    lf_handler = None
    lf_config = {}
    try:
        from langfuse.langchain import CallbackHandler
        lf_handler = CallbackHandler()
        lf_config = {
            "callbacks": [lf_handler],
            "metadata": {
                "langfuse_session_id": cl.context.session.id,
                "langfuse_trace_name": "finlake-analyst-query",
                "question": message.content,
            },
        }
    except Exception:
        _log.exception("LangFuse handler init failed — tracing disabled for this request")

    msg = cl.Message(content="")
    error_fallback = ""
    final_sql = ""
    final_retry_count = 0

    async for event in graph.astream_events(initial_state, config=lf_config, version="v2"):
        kind = event["event"]
        node = event["metadata"].get("langgraph_node", "")

        if kind == "on_chat_model_stream" and node == "interpret_result":
            chunk = event["data"].get("chunk")
            if chunk and chunk.content:
                await msg.stream_token(chunk.content)

        elif kind == "on_chain_end" and node == "generate_sql":
            output = event["data"].get("output", {})
            if isinstance(output, dict):
                final_sql = output.get("sql", final_sql)

        elif kind == "on_chain_end" and node == "execute_sql":
            output = event["data"].get("output", {})
            if isinstance(output, dict) and "retry_count" in output:
                final_retry_count = output.get("retry_count", final_retry_count)

        elif kind == "on_chain_end" and event.get("name") == "handle_error":
            output = event["data"].get("output", {})
            if isinstance(output, dict):
                error_fallback = output.get("analysis", "")

    try:
        if lf_handler is not None and lf_handler.last_trace_id:
            from langfuse import Langfuse
            lf_client = Langfuse()
            lf_client.create_score(
                trace_id=lf_handler.last_trace_id,
                name="retry_count",
                value=float(final_retry_count),
                data_type="NUMERIC",
                comment=final_sql[:300] if final_sql else None,
            )
            lf_client.flush()
    except Exception:
        _log.exception("LangFuse trace enrichment failed")

    if not msg.content and error_fallback:
        msg.content = error_fallback

    await msg.send()
