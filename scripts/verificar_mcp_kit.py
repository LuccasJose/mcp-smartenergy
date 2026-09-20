"""Verifica os MCPs auxiliares sem importar o motor ou ler dados privados."""

import argparse
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import tomllib

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


ROOT = Path(__file__).resolve().parents[1]


def load_servers(client):
    if client == "codex":
        with (ROOT / ".codex/config.toml").open("rb") as config_file:
            return tomllib.load(config_file)["mcp_servers"]
    relative, key = (
        (".vscode/mcp.json", "servers")
        if client == "vscode"
        else (".mcp.json", "mcpServers")
    )
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))[key]


async def check_call(session, name, arguments, expected):
    result = await session.call_tool(name, arguments)
    text = "\n".join(getattr(block, "text", "") for block in result.content)
    if result.isError or expected.lower() not in text.lower():
        raise RuntimeError(f"Falha em {name}; resultado MCP nao confirmou {expected!r}")
    print(f"OK: {name}")


async def check_context7(servers):
    server = servers["context7"]
    if server["url"] != "https://mcp.context7.com/mcp":
        raise RuntimeError("Endpoint Context7 diferente do oficial; revise antes de consultar")
    async with streamablehttp_client(server["url"]) as (reader, writer, _session_id):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=60)) as session:
            await session.initialize()
            await check_call(
                session, "resolve-library-id",
                {"libraryName": "numpy", "query": "NumPy 2 numpy.asarray documentation"},
                "/numpy/numpy",
            )
            await check_call(
                session, "query-docs",
                {"libraryId": "/numpy/numpy", "query": "numpy.asarray arguments and dtype"},
                "asarray",
            )


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["vscode", "claude", "codex"], default="vscode")
    parser.add_argument("--context7", action="store_true", help="Consulta documentacao PUBLICA pela rede")
    args = parser.parse_args()
    if not args.context7:
        parser.error("Escolha --context7")
    servers = load_servers(args.client)
    await check_context7(servers)


if __name__ == "__main__":
    asyncio.run(main())