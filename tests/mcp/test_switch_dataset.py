"""switch_dataset — troca da fazenda ativa no servidor (reset completo).

Usa dataset Parquet sintético em tmp_path (offline), no mesmo formato do
`gerar_dataset.py --completo` do FEMS.
"""

import json
import sys

import numpy as np
import pandas as pd
import pytest

_SERVER_MOD = "smarty_energy.mcp.server"

CARGAS = [
    ("Pivô", "Agrícola"), ("Bomba_Aux", "Agrícola"), ("Secadora", "Agrícola"),
    ("Quadro_Auto", "Agrícola"), ("Escritório", "Sede"), ("Cozinha", "Sede"),
    ("Quarto", "Sede"),
]


@pytest.fixture
def srv(monkeypatch, dia_fake, tarifa_fake):
    def fake_carregar(*_args, **_kwargs):
        return [dia_fake.copy() for _ in range(7)], tarifa_fake.copy()

    sys.modules.pop(_SERVER_MOD, None)
    import importlib
    server = importlib.import_module(_SERVER_MOD)
    server.initialize(loader=fake_carregar)
    return server


@pytest.fixture
def dataset_fems(tmp_path):
    """2 dias de fevereiro/2025 da fazenda FAZ-X (formato FEMS)."""
    horas = pd.date_range("2025-02-01", periods=48, freq="h")
    consumo = pd.DataFrame([
        {"id_fazenda": "FAZ-X", "data_hora": dh, "mes": dh.month, "hora": dh.hour,
         "carga": carga, "tipo": tipo, "consumo_kwh": 2.0}
        for dh in horas for carga, tipo in CARGAS
    ])
    geracao = pd.DataFrame([
        {"id_fazenda": "FAZ-X", "data_hora": dh, "mes": dh.month, "hora": dh.hour,
         "gerador_id": gid, "tipo": tipo, "energia_kwh": 1.5}
        for dh in horas
        for gid, tipo in (("SOL-MED", "solar_fv"), ("EOL-MED", "eolica"))
    ])
    fatura = pd.DataFrame([
        {"id_fazenda": "FAZ-X", "data_hora": dh, "mes": dh.month, "hora": dh.hour,
         "tarifa_rs": 1.1039 if 18 <= dh.hour <= 20 else 0.6813}
        for dh in horas
    ])
    consumo.to_parquet(tmp_path / "consumo.parquet")
    geracao.to_parquet(tmp_path / "geracao.parquet")
    fatura.to_parquet(tmp_path / "consumo_fatura.parquet")
    return tmp_path


def test_switch_troca_dataset_e_meta(srv, dataset_fems):
    out = json.loads(srv.switch_dataset(str(dataset_fems), id_fazenda="FAZ-X",
                                        mes=2))
    assert out["status"].startswith("dataset trocado")
    assert out["id_fazenda"] == "FAZ-X"
    assert out["n_dias"] == 2
    assert len(srv.get_state().dias) == 2
    assert srv.get_state().dataset_meta["id_fazenda"] == "FAZ-X"
    assert str(dataset_fems) in srv.get_state().dataset_meta["fonte"]
    info = json.loads(srv.get_dataset_info())
    assert info["id_fazenda"] == "FAZ-X"


def test_switch_reseta_estado_de_analise(srv, dataset_fems):
    sessao = srv.get_state()
    # estado "sujo": política populada, snapshot travado, experimento marcado
    estado = (0, 5, 1, 0, 0, 0)
    for ag in srv.get_state().iql.agentes.values():
        ag.q_table[estado] = np.ones(ag.n_acoes)
    srv._congelar_politica("rl_padrao")
    srv.get_state().rl_padrao_travado = True
    srv.get_state().experimento_carregado = {"exp_id": "x", "label": "x"}
    srv.get_state().run_carregado = {"origem": "fixture"}
    srv.get_state().soc_trace = 32.0
    srv.get_state().soc_trace_snapshot = 47.0
    srv.get_state().dia_atual_idx = 3
    _, _, _, info = srv.get_state().env.step(1, 0, 2)
    srv.get_state().tracker.registrar_passo(info, agente="rl_llm_mcp")

    json.loads(srv.switch_dataset(str(dataset_fems), id_fazenda="FAZ-X", mes=2))

    assert srv.get_state() is sessao
    assert all(not ag.q_table for ag in srv.get_state().iql.agentes.values())
    assert "rl_padrao" not in srv.get_state().snapshots
    assert srv.get_state().rl_padrao_travado is False
    assert srv.get_state().experimento_carregado is None
    assert srv.get_state().run_carregado is None
    assert srv.get_state().soc_trace is srv.get_state().soc_trace_snapshot is None
    assert srv.get_state().dia_atual_idx == srv.get_state().env.hora == 0
    assert not srv.get_state().tracker.passos.get("rl_llm_mcp")
    status = json.loads(srv.get_analysis_status())
    assert status["treinado"] is False
    assert status["proxima_etapa"] == "treinar"


def test_switch_fazenda_inexistente_retorna_erro(srv, dataset_fems):
    estado = (0, 5, 1, 0, 0, 0)
    agente = srv.get_state().iql.agentes["armazenamento"]
    agente.q_table[estado] = np.ones(agente.n_acoes)
    sessao = srv.get_state()
    anteriores = {nome: getattr(sessao, nome) for nome in ("dias", "tarifa_24h", "dataset_meta", "env", "iql")}
    srv.get_state().soc_trace = 37.5

    out = json.loads(srv.switch_dataset(str(dataset_fems), id_fazenda="FAZ-404",
                                        mes=2))
    assert "erro" in out
    assert srv.get_state() is sessao
    for nome, anterior in anteriores.items():
        assert getattr(sessao, nome) is anterior
    np.testing.assert_array_equal(agente.q_table[estado], np.ones(agente.n_acoes))
    assert srv.get_state().soc_trace == 37.5


def test_load_experiment_avisa_fonte_divergente(srv, dataset_fems, monkeypatch,
                                                tmp_path):
    from smarty_energy.mcp import experiments
    monkeypatch.setattr(experiments, "EXP_DIR", tmp_path / "exps")

    estado = (0, 5, 1, 0, 0, 0)
    for ag in srv.get_state().iql.agentes.values():
        ag.q_table[estado] = np.ones(ag.n_acoes)
    exp_id = json.loads(srv.save_experiment(label="da-fazenda-fake"))["exp_id"]

    # troca de fazenda e recarrega o modelo antigo → deve avisar
    json.loads(srv.switch_dataset(str(dataset_fems), id_fazenda="FAZ-X", mes=2))
    res = json.loads(srv.load_experiment(exp_id))
    assert "erro" not in res
    assert any("outra fonte de dados" in a for a in res["avisos_fisica"])
