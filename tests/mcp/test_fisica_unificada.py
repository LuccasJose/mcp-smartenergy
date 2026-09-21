"""Item 2 — trava a igualdade de física entre o pipeline e a camada MCP.

Depois da junção, o servidor MCP importa o motor do pacote em vez de manter um
fork. Estes testes garantem que essa unificação não regrida: se alguém
reintroduzir uma config/env/agents própria dentro de `smarty_energy/mcp/`, ou
mudar um valor físico só de um lado, algum destes testes quebra.
"""

import importlib
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from smarty_energy import config as pkg_config
from smarty_energy import environment as pkg_env
from smarty_energy import agents as pkg_agents

_SERVER_MOD = "smarty_energy.mcp.server"


@pytest.fixture
def arquitetura_isolada(tmp_path):
    raiz = Path(__file__).resolve().parents[2]
    origem = raiz / "src" / "smarty_energy"
    pacote = tmp_path / "smarty_energy"
    for arquivo in origem.rglob("*.py"):
        destino = pacote / arquivo.relative_to(origem)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(arquivo, destino)
    shutil.copyfile(raiz / "pyproject.toml", tmp_path / "pyproject.toml")
    inicializador = pacote / "__init__.py"
    inicializador.write_text(
        'raise AssertionError("O verificador nao deve executar o produto")\n'
        + inicializador.read_text(encoding="utf-8"), encoding="utf-8",
    )
    return tmp_path


def _verificar_imports(diretorio, contrato=None):
    argumentos = [
        sys.executable, "-c",
        "from importlinter.cli import lint_imports_command; lint_imports_command()",
        "--config", "pyproject.toml", "--no-cache",
    ]
    if contrato is not None:
        argumentos.extend(["--contract", contrato])
    ambiente = dict(os.environ, PYTHONPATH=str(diretorio), PYTHON_DOTENV_DISABLED="1")
    return subprocess.run(
        argumentos, cwd=diretorio, env=ambiente, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
    )


def test_contratos_arquitetura_aceitam_codigo_atual_sem_executar(arquitetura_isolada):
    resultado = _verificar_imports(arquitetura_isolada)

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "4 kept, 0 broken" in resultado.stdout


@pytest.mark.parametrize("indireto", [False, True], ids=["direto", "indireto"])
@pytest.mark.parametrize("contrato, origem, proibido, regra", [
    ("motor-sem-adaptadores", "battery.py", "smarty_energy.mcp.state", "A-DEP-001"),
    ("motor-sem-adaptadores", "agents/q_learning.py", "smarty_energy.mcp.state", "A-DEP-001"),
    ("estado-sem-servidor", "mcp/state.py", "smarty_energy.mcp.server", "A-DEP-002"),
    ("backend-sem-clientes", "mcp/server.py", "smarty_energy.mcp.dashboard.state", "A-DEP-003"),
    ("clientes-sem-motor", "mcp/dashboard/pages/4_Trace_Diario.py", "smarty_energy.environment", "A-DEP-004"),
    ("clientes-sem-motor", "mcp/dashboard/pages/4_Trace_Diario.py", "smarty_energy.agents.system", "A-DEP-004"),
])
def test_contratos_arquitetura_rejeitam_imports(arquitetura_isolada, indireto, contrato, origem, proibido, regra):
    pacote = arquitetura_isolada / "smarty_energy"
    destino_import = proibido
    if indireto:
        (pacote / "_architecture_probe.py").write_text(
            f"import {proibido}\n", encoding="utf-8",
        )
        destino_import = "smarty_energy._architecture_probe"
    arquivo = pacote / origem
    arquivo.write_text(
        arquivo.read_text(encoding="utf-8") + f"\nimport {destino_import}\n",
        encoding="utf-8",
    )

    resultado = _verificar_imports(arquitetura_isolada, contrato)

    assert resultado.returncode == 1, resultado.stdout + resultado.stderr
    assert regra in resultado.stdout
    assert "0 kept, 1 broken" in resultado.stdout


@pytest.fixture
def srv(monkeypatch, dia_fake, tarifa_fake):
    """Servidor MCP inicializado explicitamente com fixtures sinteticas."""
    def fake_carregar(*_a, **_k):
        return [dia_fake.copy() for _ in range(3)], tarifa_fake.copy()

    sys.modules.pop(_SERVER_MOD, None)
    server = importlib.import_module(_SERVER_MOD)
    server.initialize(loader=fake_carregar)
    return server


# ── Identidade dos objetos: o servidor usa o motor do pacote, não um fork ──

def test_servidor_usa_env_e_config_do_pacote(srv):
    assert srv.FazendaEnergyEnv is pkg_env.FazendaEnergyEnv
    assert srv.CONFIG is pkg_config.CONFIG
    assert srv.BOMBA_HORAS_ON is pkg_config.BOMBA_HORAS_ON
    assert srv.IQLSystem is pkg_agents.IQLSystem
    # O total de estados vem da fonte única do env, não de um número solto.
    assert srv.N_ESTADOS_TOTAL == pkg_env.ESPACO_ESTADOS_TOTAL


def test_mcp_nao_tem_modulo_de_fisica_proprio():
    """Não deve existir smarty_energy.mcp.{config,environment,energy_env,agents}."""
    for nome in ("config", "environment", "energy_env", "agents"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"smarty_energy.mcp.{nome}")


# ── describe_schema espelha o CONFIG (nada hardcoded divergente) ──

def test_describe_schema_reflete_config(srv):
    schema = json.loads(srv.describe_schema())
    fis = schema["parametros_fisicos"]
    for chave in ("soc_min_pct", "soc_max_pct", "bateria_cap_kwh", "pcc_max_kw",
                  "pivo_nominal_kw", "bomba_cap_nominal_kw", "secador_max_kw",
                  "secador_meta_kwh"):
        assert fis[chave] == pkg_config.CONFIG[chave], f"{chave} divergiu no schema"
    assert schema["estado_discreto"]["n_total"] == pkg_env.ESPACO_ESTADOS_TOTAL
    assert "18-19" in schema["estado_discreto"]["buckets"]["h"]


# ── Comportamento idêntico: mesmo dia, mesmas ações → mesmo histórico ──

def _semear_qtables(agentes: dict, seed: int = 7) -> None:
    """Preenche as Q-tables com valores determinísticos para todo o espaço.

    Um agente recém-criado tem Q-table zerada, e `argmax` de um vetor de zeros
    devolve sempre a ação 0 — a política fica degenerada em `(0, 0, 0)`. Semear
    faz a política variar por estado, exercitando carga *e* descarga da bateria,
    os cortes de carga e os três tetos do gerente.
    """
    rng = np.random.default_rng(seed)
    for ag in agentes.values():
        for estado in itertools.product(*(range(n) for n in pkg_env.BUCKETS_ESTADO)):
            ag.q_table[estado] = rng.normal(size=ag.n_acoes)


def test_compare_strategies_bate_com_o_pipeline(srv):
    """As 3 estratégias custam o mesmo pelo MCP e pelo pipeline.

    O teste acima trava a física passo a passo; este trava o **número que sai
    na ponta** — o custo médio diário que o TCC reporta. Os dois caminhos são
    independentes de propósito:

      MCP      : `compare_strategies` → `IQLSystem.avaliar` → `avaliar_politica`,
                 com o cfg do servidor (`ajustar_decay(CONFIG, …)`, um dict
                 *copiado*, não o CONFIG do pacote);
      pipeline : wrappers `rodar_*_mes` → `resumo_mes`, com o CONFIG do pacote.

    Basta alguém mudar um parâmetro físico só de um lado, ou trocar o protocolo
    de propagação de SoC em um dos caminhos, para os números descolarem aqui.
    Compara as 4 métricas do resumo, não só o custo.
    """
    from smarty_energy.evaluation import (
        resumo_mes, rodar_rl_mes, rodar_heuristico_mes, rodar_sem_agente_mes,
    )

    # Q-tables semeadas: sem isso os agentes zerados escolhem (0,0,0) em todo
    # estado, e a comparação exercitaria um caminho só — nunca descarregaria a
    # bateria, por exemplo. Com valores pseudo-aleatórios determinísticos a
    # política varia entre estados e cobre as 3 ações de cada agente.
    _semear_qtables(srv.get_state().iql.agentes)

    dias, tarifa = srv.get_state().dias, srv.get_state().tarifa_24h
    mcp = json.loads(srv.compare_strategies(n_dias=len(dias), propagar_soc=True))

    pipeline = {
        "RL_LLM_MCP": resumo_mes(rodar_rl_mes(dias, tarifa, srv.get_state().iql.agentes)),
        "Heuristico": resumo_mes(rodar_heuristico_mes(dias, tarifa)),
        "SemAgente":  resumo_mes(rodar_sem_agente_mes(dias, tarifa)),
    }
    # resumo_mes devolve (custo, rede, violações, reward) — mesma ordem das
    # chaves correspondentes em avaliar_politica.
    chaves = ("custo_medio_dia_rs", "rede_media_dia_kwh",
              "violacoes_soc_media_h_dia", "reward_medio_dia")

    for nome, valores_pipeline in pipeline.items():
        for chave, v_pipeline in zip(chaves, valores_pipeline):
            v_mcp = mcp[nome][chave]
            assert v_mcp == pytest.approx(v_pipeline, abs=1e-9), (
                f"{nome}.{chave}: MCP {v_mcp} != pipeline {v_pipeline}"
            )


def test_env_do_servidor_igual_ao_do_pacote(srv, dia_fake, tarifa_fake):
    acoes = [(0, 0, 2), (1, 3, 1), (2, 5, 0), (0, 7, 2)] * 6  # 24 passos

    # Env do pacote, direto.
    env_pkg = pkg_env.FazendaEnergyEnv(dia_fake.copy(), tarifa_fake.copy(), pkg_config.CONFIG)
    env_pkg.reset()
    for a in acoes:
        env_pkg.step(*a)

    # Env do servidor, dirigido pelas tools (dia 0 == dia_fake).
    srv.select_day(0)
    srv.reset_environment()
    for a in acoes:
        srv.step_environment(*a)

    assert len(env_pkg.historico) == len(srv.get_state().env.historico) == 24
    for h_pkg, h_srv in zip(env_pkg.historico, srv.get_state().env.historico):
        assert h_pkg["custo_r"] == pytest.approx(h_srv["custo_r"])
        assert h_pkg["reward"] == pytest.approx(h_srv["reward"])
        assert h_pkg["consumo_kw"] == pytest.approx(h_srv["consumo_kw"])
        assert h_pkg["soc"] == pytest.approx(h_srv["soc"])
