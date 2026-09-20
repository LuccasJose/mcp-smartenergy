"""Contratos MCP pelo transporte real, com dados e processos isolados."""

import asyncio
from datetime import timedelta
from importlib.metadata import version
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading

import httpx
import numpy as np
import pandas as pd
import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamable_http_client
from packaging.requirements import Requirement

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


@pytest.mark.parametrize("manifesto", ["requirements-dev", "extra-dev"])
def test_dependencias_dev_exigem_api_mcp_utilizada(manifesto):
    raiz = Path(__file__).resolve().parents[2]
    if manifesto == "requirements-dev":
        entradas = (raiz / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
        dependencias = [Requirement(linha) for linha in entradas if linha.strip() and not linha.startswith(("-", "#"))]
    else:
        config = tomllib.loads((raiz / "pyproject.toml").read_text(encoding="utf-8"))
        dependencias = [Requirement(entrada) for entrada in config["project"]["optional-dependencies"]["dev"]]
    sdk = next(dependencia for dependencia in dependencias if dependencia.name == "mcp")
    assert "1.9.0" not in sdk.specifier
    assert "1.30.0" in sdk.specifier
    assert "2.0.0" not in sdk.specifier
    assert version("mcp") in sdk.specifier


@pytest.fixture
def dados_transporte(tmp_path, dia_fake, tarifa_fake):
    arquivo = tmp_path / "fixture.json"
    arquivo.write_text(json.dumps({
        "dias": [json.loads(dia_fake.to_json(orient="records", date_format="iso"))],
        "tarifa": tarifa_fake.tolist(),
    }), encoding="utf-8")
    return arquivo


def _ambiente_isolado(arquivo):
    return {
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONIOENCODING": "utf-8",
        "MPLBACKEND": "Agg",
        "FEMS_DATASET_DIR": "",
        "SHEET_ID": "",
        "DATA_PATH": str(arquivo.parent / "nao-ler.xlsx"),
        "OUTPUT_DIR": str(arquivo.parent / "outputs"),
        "ID_FAZENDA": "FAZ-TEST",
        "MCP_N_EPISODIOS": "2",
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": "0",
        "MCP_TRANSPORT": "stdio",
    }


async def _chamar_json(sessao, nome, argumentos=None):
    resposta = await sessao.call_tool(nome, arguments=argumentos or {})
    assert not resposta.isError, resposta
    texto = "".join(bloco.text for bloco in resposta.content if isinstance(bloco, types.TextContent))
    return json.loads(texto)


async def _verificar_sessao(sessao):
    inicio = await sessao.initialize()
    assert inicio.serverInfo.name == "mcpsmartenergy"
    ferramentas = (await sessao.list_tools()).tools
    catalogo = {ferramenta.name: ferramenta for ferramenta in ferramentas}
    assert len(catalogo) == 45
    assert {"plan_dataset_splits", "get_split_experiment", "train_split_experiment",
            "evaluate_split_test"} <= catalogo.keys()
    assert catalogo["plan_dataset_splits"].inputSchema["required"] == ["metodos"]
    assert catalogo["plan_dataset_splits"].inputSchema["properties"]["dia_fim_treino"]["default"] == 24
    assert catalogo["plan_dataset_splits"].inputSchema["properties"]["dia_fim_validacao"]["default"] == 27
    assert catalogo["evaluate_split_test"].inputSchema["properties"]["confirmar"]["default"] is False
    assert {"get_dataset_info", "step_environment", "get_observation", "reset_environment"} <= catalogo.keys()
    assert set(catalogo["step_environment"].inputSchema["required"]) == {"a_arm", "a_cons", "a_ger"}
    assert "initialize" not in catalogo and "get_state" not in catalogo

    dados = await _chamar_json(sessao, "get_dataset_info")
    assert dados["id_fazenda"] == "FAZ-TEST"
    assert dados["n_dias"] == 1
    assert len(dados["tarifa_horaria_rs_kwh"]) == 24
    assert (await _chamar_json(sessao, "get_observation"))["obs"]["hora"] == 0

    plano_invalido = await _chamar_json(sessao, "plan_dataset_splits", {"metodos": []})
    assert "erro" in plano_invalido

    erro = await _chamar_json(sessao, "step_environment", {"a_arm": 6, "a_cons": 0, "a_ger": 2})
    assert "a_arm" in erro["erro"]
    assert (await _chamar_json(sessao, "get_observation"))["obs"]["hora"] == 0

    invalido = await sessao.call_tool("step_environment", arguments={"a_arm": "invalido", "a_cons": 0, "a_ger": 2})
    assert invalido.isError
    desconhecida = await sessao.call_tool("fixture_tool_inexistente", arguments={})
    assert desconhecida.isError
    assert (await _chamar_json(sessao, "get_observation"))["obs"]["hora"] == 0

    passo = await _chamar_json(sessao, "step_environment", {"a_arm": 5, "a_cons": 0, "a_ger": 2})
    assert set(passo) == {"reward", "done", "next_state_discrete", "obs", "info"}
    assert passo["done"] is False
    assert passo["obs"]["hora"] == 1
    assert isinstance(passo["info"]["em_pico_tarifa"], bool)
    assert len(passo["next_state_discrete"]) == 6
    assert (await _chamar_json(sessao, "get_observation"))["obs"]["hora"] == 1

    reinicio = await _chamar_json(sessao, "reset_environment")
    assert reinicio["estado"]["hora"] == 0
    await sessao.send_ping()


def test_stdio_handshake_tools_erros_e_estado(dados_transporte):
    parametros = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve()), "--serve-stdio", str(dados_transporte)],
        cwd=dados_transporte.parent,
        env=_ambiente_isolado(dados_transporte),
    )

    async def executar():
        async with stdio_client(parametros) as (leitura, escrita):
            async with ClientSession(leitura, escrita, read_timeout_seconds=timedelta(seconds=15)) as sessao:
                await _verificar_sessao(sessao)

    asyncio.run(asyncio.wait_for(executar(), timeout=45))
    assert dados_transporte.with_suffix(".stopped").is_file()


@pytest.fixture
def servidor_http(dados_transporte):
    ambiente = {**get_default_environment(), **_ambiente_isolado(dados_transporte)}
    ambiente["MCP_TRANSPORT"] = "streamable-http"
    prontidao = queue.Queue()
    with dados_transporte.with_suffix(".stderr").open("w", encoding="utf-8") as log:
        processo = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve-http", str(dados_transporte)],
            cwd=dados_transporte.parent, env=ambiente,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
            text=True, encoding="utf-8", bufsize=1,
        )

        def ler_prontidao():
            for linha in processo.stdout:
                if linha.startswith("TRANSPORT_READY:"):
                    prontidao.put(int(linha.partition(":")[2]))
            prontidao.put(None)

        leitor = threading.Thread(target=ler_prontidao, daemon=True)
        leitor.start()
        try:
            porta = prontidao.get(timeout=30)
            assert porta is not None, "Servidor encerrou antes de anunciar prontidao"
            yield f"http://127.0.0.1:{porta}/mcp"
        finally:
            try:
                if processo.poll() is None:
                    try:
                        processo.stdin.write("stop\n")
                        processo.stdin.flush()
                    except (BrokenPipeError, OSError):
                        pass
                    processo.stdin.close()
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.terminate()
                try:
                    processo.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    processo.kill()
                    processo.wait(timeout=5)
            finally:
                leitor.join(timeout=5)
                processo.stdout.close()
                if not processo.stdin.closed:
                    processo.stdin.close()
            assert not leitor.is_alive()
            assert processo.returncode == 0
            assert dados_transporte.with_suffix(".stopped").is_file()


def test_http_sdk_e_cliente_dashboard(servidor_http, monkeypatch):
    from smarty_energy.mcp.dashboard import mcp_client

    async def executar():
        async with httpx.AsyncClient(timeout=15, trust_env=False) as cliente:
            async with streamable_http_client(servidor_http, http_client=cliente) as (leitura, escrita, sessao_id):
                async with ClientSession(leitura, escrita, read_timeout_seconds=timedelta(seconds=15)) as sessao:
                    await _verificar_sessao(sessao)
                    assert sessao_id() is not None

    asyncio.run(asyncio.wait_for(executar(), timeout=45))
    monkeypatch.setattr(mcp_client, "MCP_SERVER_URL", servidor_http)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")

    assert mcp_client.ping() is True
    dados = mcp_client.call_tool("get_dataset_info")
    assert dados["id_fazenda"] == "FAZ-TEST"
    with pytest.raises(mcp_client.MCPServerError, match="a_arm"):
        mcp_client.call_tool("step_environment", a_arm=6, a_cons=0, a_ger=2)
    with pytest.raises(mcp_client.MCPServerError, match="fixture_tool_inexistente"):
        mcp_client.call_tool("fixture_tool_inexistente")
    assert mcp_client.call_tool("get_observation")["obs"]["hora"] == 0
    passo = mcp_client.call_tool("step_environment", a_arm=5, a_cons=0, a_ger=2)
    assert passo["obs"]["hora"] == 1
    assert mcp_client.call_tool("get_observation")["obs"]["hora"] == 1
    assert mcp_client.call_tool("reset_environment")["estado"]["hora"] == 0


def _servir_fixture(arquivo, transporte):
    from smarty_energy.mcp import server

    payload = json.loads(arquivo.read_text(encoding="utf-8"))

    def carregar_fixture():
        return [pd.DataFrame(dia) for dia in payload["dias"]], np.array(payload["tarifa"])

    def proibir_loader_padrao():
        raise AssertionError("O teste nao pode carregar a fonte de dados real")

    server.carregar_dados = proibir_loader_padrao
    server.initialize(loader=carregar_fixture)
    if transporte == "--serve-http":
        import uvicorn

        class ServidorObservado(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started:
                    porta = self.servers[0].sockets[0].getsockname()[1]
                    print(f"TRANSPORT_READY:{porta}", flush=True)
                    self.pedido_de_parada = asyncio.create_task(self.aguardar_parada())

            async def aguardar_parada(self):
                await asyncio.to_thread(sys.stdin.readline)
                self.should_exit = True

        uvicorn.Server = ServidorObservado
    try:
        server.main(["--stdio"] if transporte == "--serve-stdio" else [])
    finally:
        arquivo.with_suffix(".stopped").write_text("stopped", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("--serve-stdio", "--serve-http"):
        raise SystemExit("Use --serve-stdio ou --serve-http com o caminho da fixture sintetica")
    _servir_fixture(Path(sys.argv[2]), sys.argv[1])