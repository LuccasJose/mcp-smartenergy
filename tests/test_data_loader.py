"""Testes do carregamento de dados (data_loader) sobre a base real local.

Todos os testes usam a fixture `dados_reais` (offline) — são pulados
automaticamente se a base local não estiver presente.
"""

import numpy as np
import pandas as pd

from smarty_energy.config import CONFIG

COLUNAS_ESPERADAS = {
    "hora", "solar_kw", "eolico_kw", "pivo_kw", "captacao_kw",
    "sede_kw", "secador_kw", "silo_kw", "data",
}


def test_carrega_31_dias(dias_reais):
    assert len(dias_reais) == 31


def test_cada_dia_tem_24_horas(dias_reais):
    for dia in dias_reais:
        assert len(dia) == 24
        assert list(dia["hora"]) == list(range(24))


def test_colunas_presentes(dias_reais):
    for dia in dias_reais:
        assert COLUNAS_ESPERADAS.issubset(set(dia.columns))


def test_sem_valores_nulos_ou_negativos(dias_reais):
    numericas = [
        "solar_kw", "eolico_kw", "pivo_kw", "captacao_kw",
        "sede_kw", "secador_kw", "silo_kw",
    ]
    for dia in dias_reais:
        sub = dia[numericas]
        assert not sub.isna().any().any(), "Há valores NaN nas cargas/geração"
        assert (sub.to_numpy() >= 0).all(), "Há valores negativos nas cargas/geração"


def test_tarifa_formato_e_valores(tarifa_real):
    assert isinstance(tarifa_real, np.ndarray)
    assert tarifa_real.shape == (24,)
    assert np.all(tarifa_real > 0), "Tarifa deve ser sempre positiva"


def test_tarifa_pico_maior_que_fora_pico(tarifa_real):
    """A tarifa no pico (18h–21h) deve ser maior que a média fora do pico."""
    pico = tarifa_real[18:21].mean()
    fora_pico = np.concatenate([tarifa_real[:18], tarifa_real[21:]]).mean()
    assert pico > fora_pico


def test_geracao_solar_zero_de_madrugada(dias_reais):
    """Não deve haver geração solar entre 0h e 4h."""
    for dia in dias_reais:
        madrugada = dia.loc[dia["hora"] < 5, "solar_kw"]
        assert (madrugada == 0).all()


def test_datas_sao_de_janeiro_2025(dias_reais):
    for dia in dias_reais:
        data = pd.Timestamp(dia["data"].iloc[0])
        assert data.year == 2025
        assert data.month == 1
