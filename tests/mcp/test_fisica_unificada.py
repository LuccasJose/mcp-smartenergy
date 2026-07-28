"""Item 2 — trava a igualdade de física entre o pipeline e a camada MCP.

Depois da junção, o servidor MCP importa o motor do pacote em vez de manter um
fork. Estes testes garantem que essa unificação não regrida: se alguém
reintroduzir uma config/env/agents própria dentro de `smarty_energy/mcp/`, ou
mudar um valor físico só de um lado, algum destes testes quebra.
"""

import importlib
import json
import sys

import pytest

from smarty_energy import config as pkg_config
from smarty_energy import environment as pkg_env
from smarty_energy import agents as pkg_agents

_SERVER_MOD = "smarty_energy.mcp.server"


@pytest.fixture
def srv(monkeypatch, dia_fake, tarifa_fake):
    """Servidor MCP importado com o dataset trocado por fixtures sintéticas."""
    from smarty_energy import data_loader

    def fake_carregar(*_a, **_k):
        return [dia_fake.copy() for _ in range(3)], tarifa_fake.copy()

    monkeypatch.setattr(data_loader, "carregar_dados", fake_carregar)
    sys.modules.pop(_SERVER_MOD, None)
    return importlib.import_module(_SERVER_MOD)


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


# ── Comportamento idêntico: mesmo dia, mesmas ações → mesmo histórico ──

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

    assert len(env_pkg.historico) == len(srv.env.historico) == 24
    for h_pkg, h_srv in zip(env_pkg.historico, srv.env.historico):
        assert h_pkg["custo_r"] == pytest.approx(h_srv["custo_r"])
        assert h_pkg["reward"] == pytest.approx(h_srv["reward"])
        assert h_pkg["consumo_kw"] == pytest.approx(h_srv["consumo_kw"])
        assert h_pkg["soc"] == pytest.approx(h_srv["soc"])
