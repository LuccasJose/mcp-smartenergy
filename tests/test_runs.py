"""Compatibilidade de runs persistidos com a codificação atual de estados."""

import numpy as np
import pytest

from smarty_energy import runs
from smarty_energy.agents import AgenteQL, construir_agentes
from smarty_energy.config import CONFIG
from smarty_energy.environment import STATE_ENCODING_VERSION
from smarty_energy.runs import carregar_run, ler_meta, salvar_run, verificar_compatibilidade


@pytest.fixture
def runs_isolados(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runs, "_LATEST", tmp_path / "runs" / "latest.txt")
    return runs.RUNS_DIR


def test_salvar_run_registra_versao_da_codificacao(runs_isolados):
    hist = {"n_episodios": 1, "config_completo": {}}

    run_id = salvar_run(construir_agentes(), hist, run_id="run_novo")

    assert ler_meta(run_id)["state_encoding_version"] == STATE_ENCODING_VERSION


def test_run_roundtrip_preserva_politica_historico_e_config(runs_isolados):
    agentes = construir_agentes()
    estado = (2, 5, 1, 0, 1, 2)
    for indice, agente in enumerate(agentes.values(), start=1):
        agente.q_table[estado][:] = np.arange(agente.n_acoes, dtype=float) + indice
        agente.epsilon = 0.1 * indice
        agente.n_updates = 10 * indice
    historico = {
        "n_episodios": 2,
        "rewards": [-5.0, -3.0],
        "custos": [2.0, 1.0],
        "config_completo": dict(CONFIG),
    }

    run_id = salvar_run(agentes, historico, run_id="sintetico", fonte_dados="fixture")
    restaurados = construir_agentes()
    resultado = carregar_run(run_id, restaurados)

    assert resultado == historico
    meta = ler_meta(run_id)
    assert meta["config_completo"] == CONFIG
    assert meta["fonte_dados"] == "fixture"
    assert meta["state_encoding_version"] == STATE_ENCODING_VERSION
    assert (runs_isolados / "latest.txt").read_text(encoding="utf-8").strip() == run_id
    assert {arquivo.name for arquivo in (runs_isolados / run_id).iterdir()} == {
        "qtable_armazenamento.pkl", "qtable_consumo.pkl", "qtable_gerente.pkl",
        "training_history.pkl", "meta.json",
    }
    for nome, original in agentes.items():
        restaurado = restaurados[nome]
        np.testing.assert_array_equal(restaurado.q_table[estado], original.q_table[estado])
        assert restaurado.n_acoes == original.n_acoes
        assert restaurado.epsilon == original.epsilon
        assert restaurado.n_updates == original.n_updates
        np.testing.assert_array_equal(
            restaurado.q_table[(0, 0, 0, 0, 0, 0)], np.zeros(original.n_acoes),
        )


def test_carregar_run_ausente_falha(runs_isolados):
    with pytest.raises(FileNotFoundError, match="ausente"):
        carregar_run("ausente", construir_agentes())


@pytest.mark.parametrize("nome, n_acoes", [
    ("armazenamento", 5), ("consumo", 4), ("gerente", 2),
])
def test_carregar_run_rejeita_numero_de_acoes(runs_isolados, nome, n_acoes):
    agentes = construir_agentes()
    agentes[nome] = AgenteQL(n_acoes, nome, CONFIG)
    run_id = salvar_run(
        agentes, {"config_completo": dict(CONFIG)}, run_id="acoes_antigas",
    )

    with pytest.raises(ValueError, match="n_acoes"):
        carregar_run(run_id, construir_agentes())


def test_run_com_codificacao_atual_e_aceito(monkeypatch):
    agentes = construir_agentes()
    monkeypatch.setattr(
        "smarty_energy.runs.ler_meta",
        lambda _run_id: {
            "state_encoding_version": STATE_ENCODING_VERSION,
            "config_completo": {"bateria_cap_kwh": CONFIG["bateria_cap_kwh"]},
        },
    )

    verificar_compatibilidade("run_atual", agentes)


def test_run_com_codificacao_antiga_e_rejeitado(monkeypatch):
    agentes = construir_agentes()
    monkeypatch.setattr(
        "smarty_energy.runs.ler_meta",
        lambda _run_id: {"state_encoding_version": STATE_ENCODING_VERSION - 1},
    )

    with pytest.raises(ValueError, match="codificação de estado"):
        verificar_compatibilidade("run_antigo", agentes)


@pytest.mark.parametrize("chave", [
    (0, 0, 0, 0, 0),
    (7, 0, 0, 0, 0, 0),
    (0, -1, 0, 0, 0, 0),
])
def test_run_com_chave_invalida_e_rejeitado(monkeypatch, chave):
    agentes = construir_agentes()
    agentes["armazenamento"].q_table[chave]
    monkeypatch.setattr(
        "smarty_energy.runs.ler_meta",
        lambda _run_id: {"state_encoding_version": STATE_ENCODING_VERSION},
    )

    with pytest.raises(ValueError, match="fora da discretização atual"):
        verificar_compatibilidade("run_chave_invalida", agentes)


def test_run_com_fisica_diferente_emite_aviso(monkeypatch):
    monkeypatch.setattr(
        "smarty_energy.runs.ler_meta",
        lambda _run_id: {
            "state_encoding_version": STATE_ENCODING_VERSION,
            "config_completo": {"bateria_cap_kwh": CONFIG["bateria_cap_kwh"] + 1.0},
        },
    )

    with pytest.warns(UserWarning, match="física diferente"):
        verificar_compatibilidade("run_outra_fisica", construir_agentes())


def test_run_sem_config_emite_aviso(monkeypatch):
    monkeypatch.setattr(
        "smarty_energy.runs.ler_meta",
        lambda _run_id: {"state_encoding_version": STATE_ENCODING_VERSION},
    )

    with pytest.warns(UserWarning, match="run legado"):
        verificar_compatibilidade("run_sem_config", construir_agentes())