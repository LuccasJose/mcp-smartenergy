"""Integridade do dataset FEMS versionado em dados/fems_faz_002 (fonte padrão).

Todos os testes rodam OFFLINE — validam os Parquets locais e a coerência
entre eles, sem tocar em Google Sheets ou na API do FEMS.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from smarty_energy.config import CONFIG, FEMS_DATASET_DIR, ID_FAZENDA
from smarty_energy.data_loader import _carregar_fems

DATASET = Path(__file__).resolve().parents[1] / "dados" / "fems_faz_002"

pytestmark = pytest.mark.skipif(not DATASET.is_dir(),
                                reason="dataset FEMS versionado ausente")


@pytest.fixture(scope="module")
def fems():
    dias, tarifa = _carregar_fems(str(DATASET), mes=1, id_fazenda="FAZ-002")
    return dias, tarifa


# ── Estrutura ──────────────────────────────────────────────────────────

def test_config_aponta_para_dataset_versionado():
    """O padrão do projeto agora é a cópia versionada (offline)."""
    assert FEMS_DATASET_DIR == str(DATASET)
    assert ID_FAZENDA == "FAZ-002"


def test_janeiro_completo_24h_por_dia(fems):
    dias, _ = fems
    assert len(dias) == 31
    for d in dias:
        assert len(d) == 24
        assert list(d["hora"]) == list(range(24))
    datas = [d["data"].iloc[0] for d in dias]
    assert datas == sorted(datas)                       # ordem cronológica
    assert pd.Series(datas).dt.month.eq(1).all()


def test_sem_nan_e_sem_negativos(fems):
    dias, tarifa = fems
    cols = ["solar_kw", "eolico_kw", "pivo_kw", "captacao_kw",
            "sede_kw", "secador_kw", "silo_kw"]
    for d in dias:
        assert not d[cols].isna().any().any()
        assert (d[cols] >= 0).all().all()
    assert not np.isnan(tarifa).any()
    assert (tarifa > 0).all()


# ── Física / coerência com o CONFIG ────────────────────────────────────

def test_potencias_dentro_dos_limites_fisicos(fems):
    dias, _ = fems
    tudo = pd.concat(dias)
    assert tudo["pivo_kw"].max() <= CONFIG["pivo_nominal_kw"] + 1e-6
    assert tudo["captacao_kw"].max() <= CONFIG["bomba_cap_nominal_kw"] + 1e-6
    # nenhuma carga individual excede o PCC
    for c in ("pivo_kw", "captacao_kw", "sede_kw", "secador_kw", "silo_kw"):
        assert tudo[c].max() < CONFIG["pcc_max_kw"]


def test_tarifa_azul_com_pico_18_20(fems):
    _, tarifa = fems
    assert tarifa.shape == (24,)
    pico = {h for h in range(24) if tarifa[h] > 0.9}
    assert pico == {18, 19, 20}
    assert len(set(np.round(tarifa, 4))) == 2           # só 2 patamares


def test_geracao_solar_zero_a_noite(fems):
    dias, _ = fems
    tudo = pd.concat(dias)
    noite = tudo[tudo["hora"].isin([0, 1, 2, 3, 22, 23])]
    assert noite["solar_kw"].max() == 0.0


# ── Coerência entre os parquets (loader × fatura) ──────────────────────

def test_balanco_energetico_bate_com_fatura(fems):
    """Σ(cargas) e Σ(geração) do loader devem bater com consumo_fatura."""
    dias, _ = fems
    fat = pd.read_parquet(DATASET / "consumo_fatura.parquet")
    fat = fat[(fat["id_fazenda"] == "FAZ-002") & (fat["mes"] == 1)]

    cols = ["pivo_kw", "captacao_kw", "sede_kw", "secador_kw", "silo_kw"]
    consumo_loader = sum(d[cols].to_numpy().sum() for d in dias)
    geracao_loader = sum(d[["solar_kw", "eolico_kw"]].to_numpy().sum() for d in dias)

    assert consumo_loader == pytest.approx(fat["consumo_kwh"].sum(), rel=1e-6)
    assert geracao_loader == pytest.approx(fat["geracao_kwh"].sum(), rel=1e-6)


def test_cadastro_cargas_cobre_o_modelo():
    cad = pd.read_parquet(DATASET / "cadastro_cargas.parquet")
    cargas = set(cad["carga"])
    assert {"Pivô", "Bomba_Aux", "Secadora", "Quadro_Auto"} <= cargas
    assert (cad["tipo"] == "Sede").sum() >= 3           # Escritório+Cozinha+Quarto


# ── Ponta-a-ponta: o ambiente aceita o dataset ─────────────────────────

def test_ambiente_roda_um_dia_sem_violacoes_estruturais(fems):
    from smarty_energy.environment import FazendaEnergyEnv
    dias, tarifa = fems
    env = FazendaEnergyEnv(dias[0], tarifa, CONFIG)
    env.reset()
    for _ in range(24):
        env.step(1, 0, 2)                               # manter / nada / liberal
    h = env.historico
    assert len(h) == 24
    assert all(np.isfinite(p["custo_r"]) for p in h)
    # PCC nunca violado com política passiva
    assert sum(p["pcc_violado"] for p in h) == 0
