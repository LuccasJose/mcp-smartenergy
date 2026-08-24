"""Compatibilidade de runs persistidos com a codificação atual de estados."""

import pytest

from smarty_energy.agents import construir_agentes
from smarty_energy.config import CONFIG
from smarty_energy.environment import STATE_ENCODING_VERSION
from smarty_energy.runs import ler_meta, salvar_run, verificar_compatibilidade


def test_salvar_run_registra_versao_da_codificacao(tmp_path, monkeypatch):
    import smarty_energy.runs as runs

    monkeypatch.setattr(runs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runs, "_LATEST", tmp_path / "runs" / "latest.txt")
    hist = {"n_episodios": 1, "config_completo": {}}

    run_id = salvar_run(construir_agentes(), hist, run_id="run_novo")

    assert ler_meta(run_id)["state_encoding_version"] == STATE_ENCODING_VERSION


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