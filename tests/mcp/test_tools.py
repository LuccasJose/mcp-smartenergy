"""Tools do servidor MCP (configure_*, compare_strategies, health_report).

O servidor real puxa dataset do Google Sheets no import. Para isolar,
monkey-patchamos `carregar_dados` antes de re-importar o modulo `server`.
"""

import json
import sys

import pytest


@pytest.fixture
def srv(monkeypatch, dia_fake, tarifa_fake):
    """Importa server.py com dataset substituido por fixtures sinteticas."""
    from environment import data_loader

    def fake_carregar(*_args, **_kwargs):
        meta = {
            "n_dias": 7, "id_fazenda": "TEST",
            "data_inicio": "2025-01-01", "data_fim": "2025-01-07",
            "tarifa_min_rs_kwh": 0.70, "tarifa_max_rs_kwh": 1.10,
            "horas_pico": [18, 19, 20],
        }
        return [dia_fake.copy() for _ in range(7)], tarifa_fake.copy(), meta

    monkeypatch.setattr(data_loader, "carregar_dados", fake_carregar)
    sys.modules.pop("server", None)
    import server

    # Garante pesos no default pra cada teste (CONFIG eh global mutavel)
    from config import CONFIG
    for k, v in server._DEFAULT_REWARD_WEIGHTS.items():
        CONFIG[k] = v
    return server


# --- configure_reward_weights ----------------------------------------------

def test_reward_weights_chamada_vazia_retorna_estado(srv):
    out = json.loads(srv.configure_reward_weights())
    assert out["status"] == "nenhum peso fornecido"
    assert len(out["pesos_atuais"]) == 15
    assert "defaults" in out


def test_reward_weights_valor_negativo_erra(srv):
    out = json.loads(srv.configure_reward_weights(pen_pcc=-5.0))
    assert "erro" in out
    assert "pen_pcc" in out["erro"]


def test_reward_weights_valido_persiste(srv):
    from config import CONFIG
    novo = 99.0
    out = json.loads(srv.configure_reward_weights(w_custo=novo))
    assert out["status"] == "pesos atualizados"
    assert CONFIG["w_custo"] == novo
    assert out["delta_vs_default"]["w_custo"] == round(novo - 8.0, 4)
    assert "Q-tables" in out["aviso"]


def test_reward_weights_recria_env_global(srv):
    """Apos mudar peso, env global deve refletir o novo CONFIG."""
    env_antes = srv.env
    srv.configure_reward_weights(pen_pcc=42.0)
    assert srv.env is not env_antes  # nova instancia
    assert srv.env.cfg["pen_pcc"] == 42.0


# --- health_report: detecta pesos modificados ------------------------------

def test_health_report_sem_pesos_modificados_nao_dispara_alerta(srv):
    out = json.loads(srv.health_report())
    assert out.get("pesos_reward_modificados") is None
    assert not any("pesos_reward" in a for a in out["alertas"])


def test_health_report_com_pesos_modificados_dispara_alerta(srv):
    srv.configure_reward_weights(pen_pcc=50.0, w_custo=20.0)
    out = json.loads(srv.health_report())
    assert out["pesos_reward_modificados"] is not None
    assert "pen_pcc" in out["pesos_reward_modificados"]
    assert "w_custo" in out["pesos_reward_modificados"]
    assert any("pesos_reward_modificados" in a for a in out["alertas"])


# --- compare_strategies popula 3 trackers ----------------------------------

def test_compare_strategies_popula_tres_trackers(srv):
    # Treina minimamente pra dar inicializacao plausivel ao IQL
    srv.configure_agents(n_episodios=2)
    srv.train_agents()

    out = json.loads(srv.compare_strategies(n_dias=2))
    assert "IQL" in out
    assert "Heuristico" in out
    assert "SemAgente" in out
    assert "tracker_keys" in out
    assert out["tracker_keys"] == ["iql_eval_cmp", "heuristico", "sem_agente"]

    # Os 3 trackers devem ter passos registrados
    for key in out["tracker_keys"]:
        assert len(srv.tracker.passos[key]) > 0, f"tracker {key} vazio"
        assert len(srv.tracker.episodios[key]) > 0, f"episodios de {key} vazio"


def test_compare_strategies_calcula_reducoes(srv):
    srv.configure_agents(n_episodios=2)
    srv.train_agents()
    out = json.loads(srv.compare_strategies(n_dias=2))
    assert "reducao_iql_vs_sem_pct" in out


# --- configure_agents -------------------------------------------------------

def test_configure_agents_valida_ranges(srv):
    out = json.loads(srv.configure_agents(alpha=1.5))
    assert "erro" in out
    out = json.loads(srv.configure_agents(gamma=1.0))
    assert "erro" in out


def test_configure_agents_aceita_validos(srv):
    out = json.loads(srv.configure_agents(alpha=0.2, gamma=0.9, beta=0.05))
    assert out["status"] == "agentes reconfigurados"
    for ag in srv.iql.agentes.values():
        assert ag.alpha == 0.2
        assert ag.gamma == 0.9
        assert ag.beta == 0.05
