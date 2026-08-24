"""Loader do dataset Parquet do FEMS (_carregar_fems).

Fixture sintética: 2 dias × 24h, 2 fazendas, mesmas colunas/nomes que o
`gerar_dataset.py --completo` do FEMS produz — o teste roda offline.
"""

import numpy as np
import pandas as pd
import pytest

from smarty_energy.data_loader import _carregar_fems

CARGAS = [
    ("Pivô", "Agrícola"), ("Bomba_Aux", "Agrícola"), ("Secadora", "Agrícola"),
    ("Quadro_Auto", "Agrícola"), ("Escritório", "Sede"), ("Cozinha", "Sede"),
    ("Quarto", "Sede"),
]


@pytest.fixture
def fems_dir(tmp_path):
    horas = pd.date_range("2025-01-01", periods=48, freq="h")  # jan
    horas_fev = pd.date_range("2025-02-01", periods=24, freq="h")
    todas = horas.append(horas_fev)

    consumo = pd.DataFrame([
        {"id_fazenda": faz, "data_hora": dh, "mes": dh.month, "hora": dh.hour,
         "carga": carga, "tipo": tipo, "consumo_kwh": 1.0 + dh.hour * 0.1}
        for faz in ("FAZ-002", "FAZ-009")
        for dh in todas
        for carga, tipo in CARGAS
    ])
    geracao = pd.DataFrame([
        {"id_fazenda": faz, "data_hora": dh, "mes": dh.month, "hora": dh.hour,
         "gerador_id": gid, "tipo": tipo, "energia_kwh": 2.0 if tipo == "solar_fv" else 0.5}
        for faz in ("FAZ-002", "FAZ-009")
        for dh in todas
        for gid, tipo in (("SOL-MED", "solar_fv"), ("EOL-MED", "eolica"))
    ])
    fatura = pd.DataFrame([
        {"id_fazenda": "FAZ-002", "data_hora": dh, "mes": dh.month, "hora": dh.hour,
         "tarifa_rs": 1.1039 if 18 <= dh.hour <= 20 else 0.6813}
        for dh in todas
    ])
    consumo.to_parquet(tmp_path / "consumo.parquet")
    geracao.to_parquet(tmp_path / "geracao.parquet")
    fatura.to_parquet(tmp_path / "consumo_fatura.parquet")
    return tmp_path


def test_carrega_mes_com_colunas_do_modelo(fems_dir):
    dias, tarifa = _carregar_fems(str(fems_dir), mes=1, id_fazenda="FAZ-002")
    assert len(dias) == 2                       # só janeiro
    esperadas = {"hora", "solar_kw", "eolico_kw", "pivo_kw", "captacao_kw",
                 "sede_kw", "secador_kw", "silo_kw", "data"}
    assert esperadas <= set(dias[0].columns)
    assert len(dias[0]) == 24


def test_mapeamento_de_cargas_e_geradores(fems_dir):
    dias, _ = _carregar_fems(str(fems_dir), mes=1, id_fazenda="FAZ-002")
    d = dias[0]
    assert (d["solar_kw"] == 2.0).all()
    assert (d["eolico_kw"] == 0.5).all()
    # sede = Escritório + Cozinha + Quarto (3 cargas de mesmo perfil)
    assert np.allclose(d["sede_kw"], 3 * d["pivo_kw"])


def test_tarifa_extraida_da_fatura(fems_dir):
    _, tarifa = _carregar_fems(str(fems_dir), mes=1, id_fazenda="FAZ-002")
    assert tarifa.shape == (24,)
    assert np.allclose(tarifa[18:21], 1.1039)
    assert np.allclose(tarifa[:18], 0.6813)


def test_mes_zero_carrega_tudo(fems_dir):
    dias, _ = _carregar_fems(str(fems_dir), mes=0, id_fazenda="FAZ-002")
    assert len(dias) == 3                       # 2 dias jan + 1 dia fev


def test_fazenda_inexistente_falha(fems_dir):
    with pytest.raises(ValueError, match="FAZ-404"):
        _carregar_fems(str(fems_dir), mes=1, id_fazenda="FAZ-404")
