"""Experimentos — modelos salvos (par RL padrão + RL + LLM MCP).

Round-trip completo via tools do servidor, com dataset sintético (offline)
e EXP_DIR redirecionado para tmp_path.
"""

import json
import sys

import numpy as np
import pytest

_SERVER_MOD = "smarty_energy.mcp.server"


@pytest.fixture
def srv(monkeypatch, tmp_path, dia_fake, tarifa_fake):
    """Servidor com dataset fake e experimentos gravados em tmp_path."""
    def fake_carregar(*_args, **_kwargs):
        return [dia_fake.copy() for _ in range(7)], tarifa_fake.copy()

    sys.modules.pop(_SERVER_MOD, None)
    import importlib
    server = importlib.import_module(_SERVER_MOD)
    server.initialize(loader=fake_carregar)

    from smarty_energy.mcp import experiments
    monkeypatch.setattr(experiments, "EXP_DIR", tmp_path / "experimentos")

    from smarty_energy.config import CONFIG
    for k, v in server._DEFAULT_REWARD_WEIGHTS.items():
        CONFIG[k] = v
        server.get_state().iql.cfg[k] = v
    yield server
    for k, v in server._DEFAULT_REWARD_WEIGHTS.items():
        CONFIG[k] = v
        server.get_state().iql.cfg[k] = v


def _popular_politica(server, valor: float = 1.0) -> None:
    """Simula um treino: povoa as Q-tables e o hist sem rodar episódios."""
    estado = (0, 5, 1, 0, 0, 0)
    for ag in server.get_state().iql.agentes.values():
        ag.q_table.clear()
        ag.q_table[estado] = np.full(ag.n_acoes, valor)
    server.get_state().iql.ultimo_hist = {"n_episodios": 123, "best_ep": 100,
                              "best_custo_med": 70.0}
    server.get_state().iql.soc_propagado = 61.5


def test_save_sem_treino_retorna_erro(srv):
    for ag in srv.get_state().iql.agentes.values():
        ag.q_table.clear()
    out = json.loads(srv.save_experiment())
    assert "erro" in out


def test_round_trip_restaura_os_dois_bracos(srv):
    _popular_politica(srv, valor=7.0)
    srv._congelar_politica("rl_padrao")

    out = json.loads(srv.save_experiment(label="meu-modelo"))
    assert out["status"] == "experimento salvo"
    exp_id = out["exp_id"]

    # simula restart: zera política viva, snapshot e SOC
    for ag in srv.get_state().iql.agentes.values():
        ag.q_table.clear()
    srv.get_state().snapshots.clear()
    srv.get_state().iql.soc_propagado = 50.0
    srv.get_state().iql.ultimo_hist = None

    res = json.loads(srv.load_experiment(exp_id))
    assert res["status"].startswith("experimento carregado")
    assert res["label"] == "meu-modelo"

    estado = (0, 5, 1, 0, 0, 0)
    for ag in srv.get_state().iql.agentes.values():
        assert estado in ag.q_table
        assert np.allclose(ag.q_table[estado], 7.0)
    assert "rl_padrao" in srv.get_state().snapshots
    assert np.allclose(srv.get_state().snapshots["rl_padrao"]["consumo"][estado], 7.0)
    assert srv.get_state().rl_padrao_travado is True
    assert srv.get_state().iql.soc_propagado == pytest.approx(61.5)
    assert srv.get_state().iql.ultimo_hist["n_episodios"] == 123

    status = json.loads(srv.get_analysis_status())
    assert status["treinado"] is True
    assert status["experimento_carregado"]["exp_id"] == exp_id


def test_label_default_usa_n_episodios(srv):
    _popular_politica(srv)
    out = json.loads(srv.save_experiment())
    assert out["label"] == "123ep"


def test_pesos_do_reward_sao_restaurados(srv):
    from smarty_energy.config import CONFIG
    _popular_politica(srv)
    srv.configure_reward_weights(pen_pcc=42.0)
    exp_id = json.loads(srv.save_experiment(label="pesos-custom"))["exp_id"]

    # volta o peso ao default e recarrega — deve restaurar 42.0
    srv.configure_reward_weights(pen_pcc=srv._DEFAULT_REWARD_WEIGHTS["pen_pcc"])
    assert CONFIG["pen_pcc"] == srv._DEFAULT_REWARD_WEIGHTS["pen_pcc"]

    res = json.loads(srv.load_experiment(exp_id))
    assert "erro" not in res
    assert CONFIG["pen_pcc"] == 42.0
    assert srv.get_state().iql.cfg["pen_pcc"] == 42.0


def test_list_e_rename(srv):
    _popular_politica(srv)
    a = json.loads(srv.save_experiment(label="a"))["exp_id"]
    b = json.loads(srv.save_experiment(label="b"))["exp_id"]

    lista = json.loads(srv.list_experiments())
    assert lista["n"] == 2
    assert lista["experimentos"][0]["exp_id"] == b     # mais recente primeiro
    assert lista["experimentos"][1]["exp_id"] == a

    out = json.loads(srv.rename_experiment(a, "novo-nome"))
    assert out["label"] == "novo-nome"
    lista = json.loads(srv.list_experiments())
    labels = {m["exp_id"]: m["label"] for m in lista["experimentos"]}
    assert labels[a] == "novo-nome"


def test_encoding_incompativel_recusa_load(srv):
    from smarty_energy.mcp import experiments
    _popular_politica(srv)
    exp_id = json.loads(srv.save_experiment())["exp_id"]

    meta = experiments._ler_meta(exp_id)
    meta["state_encoding_version"] = 1
    experiments._escrever_meta(exp_id, meta)

    res = json.loads(srv.load_experiment(exp_id))
    assert "erro" in res
    assert "state_encoding_version" in res["erro"]


def test_load_sem_experimentos_retorna_erro(srv):
    res = json.loads(srv.load_experiment())
    assert "erro" in res
