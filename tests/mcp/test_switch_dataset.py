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
    from smarty_energy import data_loader

    def fake_carregar(*_args, **_kwargs):
        return [dia_fake.copy() for _ in range(7)], tarifa_fake.copy()

    monkeypatch.setattr(data_loader, "carregar_dados", fake_carregar)
    sys.modules.pop(_SERVER_MOD, None)
    import importlib
    return importlib.import_module(_SERVER_MOD)


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
    assert len(srv.DIAS) == 2
    assert srv.DATASET_META["id_fazenda"] == "FAZ-X"
    assert str(dataset_fems) in srv.DATASET_META["fonte"]
    info = json.loads(srv.get_dataset_info())
    assert info["id_fazenda"] == "FAZ-X"


def test_switch_reseta_estado_de_analise(srv, dataset_fems):
    # estado "sujo": política populada, snapshot travado, experimento marcado
    estado = (0, 5, 1, 0, 0, 0)
    for ag in srv.iql.agentes.values():
        ag.q_table[estado] = np.ones(ag.n_acoes)
    srv._congelar_politica("rl_padrao")
    srv._rl_padrao_travado = True
    srv._experimento_carregado = {"exp_id": "x", "label": "x"}

    json.loads(srv.switch_dataset(str(dataset_fems), id_fazenda="FAZ-X", mes=2))

    assert all(not ag.q_table for ag in srv.iql.agentes.values())
    assert "rl_padrao" not in srv._snapshots
    assert srv._rl_padrao_travado is False
    assert srv._experimento_carregado is None
    status = json.loads(srv.get_analysis_status())
    assert status["treinado"] is False
    assert status["proxima_etapa"] == "treinar"


def test_switch_fazenda_inexistente_retorna_erro(srv, dataset_fems):
    out = json.loads(srv.switch_dataset(str(dataset_fems), id_fazenda="FAZ-404",
                                        mes=2))
    assert "erro" in out


def test_load_experiment_avisa_fonte_divergente(srv, dataset_fems, monkeypatch,
                                                tmp_path):
    from smarty_energy.mcp import experiments
    monkeypatch.setattr(experiments, "EXP_DIR", tmp_path / "exps")

    estado = (0, 5, 1, 0, 0, 0)
    for ag in srv.iql.agentes.values():
        ag.q_table[estado] = np.ones(ag.n_acoes)
    exp_id = json.loads(srv.save_experiment(label="da-fazenda-fake"))["exp_id"]

    # troca de fazenda e recarrega o modelo antigo → deve avisar
    json.loads(srv.switch_dataset(str(dataset_fems), id_fazenda="FAZ-X", mes=2))
    res = json.loads(srv.load_experiment(exp_id))
    assert "erro" not in res
    assert any("outra fonte de dados" in a for a in res["avisos_fisica"])
