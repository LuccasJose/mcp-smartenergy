"""Cliente MCP síncrono usado pelo dashboard Streamlit.

O dashboard NÃO importa mais `agents/`, `environment/` ou `metrics/`
diretamente. Toda métrica, log ou estado de treino exibido na UI vem de
uma chamada de ferramenta contra o servidor MCP (`server.py`) rodando
como processo HTTP separado — o MCP é o intermediário obrigatório entre
o agente/treinamento e qualquer saída (dashboard ou LLM-juiz).

Requer o servidor rodando antes do dashboard:
    python server.py
"""

from __future__ import annotations

import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


class MCPServerError(RuntimeError):
    """Falha ao chamar uma ferramenta do servidor MCP (conexão ou aplicação)."""


async def _call_tool_async(tool_name: str, arguments: dict) -> dict:
    try:
        async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
    except MCPServerError:
        raise
    except Exception as e:
        raise MCPServerError(
            f"Não foi possível conectar ao servidor MCP em {MCP_SERVER_URL}. "
            f"Rode `python server.py` antes de usar o dashboard. Detalhe: {e}"
        ) from e

    if result.isError:
        detalhe = "".join(getattr(c, "text", str(c)) for c in result.content)
        raise MCPServerError(f"Ferramenta '{tool_name}' retornou erro: {detalhe}")

    texto = "".join(c.text for c in result.content if hasattr(c, "text"))
    try:
        payload = json.loads(texto)
    except json.JSONDecodeError as e:
        raise MCPServerError(f"Resposta não-JSON de '{tool_name}': {texto[:200]}") from e

    if isinstance(payload, dict) and "erro" in payload:
        raise MCPServerError(f"{tool_name}: {payload['erro']}")

    return payload


def call_tool(tool_name: str, **arguments) -> dict:
    """Chama uma ferramenta MCP e retorna o payload JSON já decodificado.

    Abre uma sessão MCP nova por chamada — mais simples e robusto do que
    manter uma sessão persistente entre reruns do Streamlit, ao custo de
    latência extra por ação (aceitável para operações disparadas por botão).
    """
    return asyncio.run(_call_tool_async(tool_name, arguments))


def ping() -> bool:
    """True se o servidor MCP está acessível em MCP_SERVER_URL."""
    try:
        call_tool("get_dataset_info")
        return True
    except MCPServerError:
        return False
