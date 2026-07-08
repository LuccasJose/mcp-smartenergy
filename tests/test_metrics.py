"""Testes das métricas primárias 4.1 (módulo `metrics`).

Estes testes fixam as DEFINIÇÕES operacionais (requisito P3 do plano): se uma
fórmula mudar sem intenção, um invariante quebra. Rodam sobre um dia sintético
controlado (`dia_fake`) e sobre os 31 dias reais, com várias políticas.
"""

import numpy as np
import pytest

from smarty_energy.config import CONFIG
from smarty_energy.environment import FazendaEnergyEnv
from smarty_energy.evaluation import rodar_sem_agente, rodar_heuristico
from smarty_energy.metrics import (
    metricas_dia, resumo_metricas, serie_por_dia, gap_otimalidade,
)

EPS = 1e-6


def _rodar(dia, tarifa, a_arm=1, a_cons=0, a_ger=2):
    env = FazendaEnergyEnv(dia, tarifa, CONFIG)
    env.reset()
    for _ in range(24):
        env.step(a_arm, a_cons, a_ger)
    return env.historico


# ── Estrutura e domínio ────────────────────────────────────────────────

def test_metricas_dia_tem_chaves_esperadas(dia_fake, tarifa_fake):
    m = metricas_dia(_rodar(dia_fake, tarifa_fake))
    for chave in ("custo_total_r", "autossuficiencia", "autoconsumo",
                  "pico_demanda_kw", "energia_importada", "energia_exportada",
                  "energia_cortada", "ciclos_bateria", "violacoes_soc"):
        assert chave in m


def test_fracoes_dentro_de_zero_um(dia_fake, tarifa_fake):
    m = metricas_dia(_rodar(dia_fake, tarifa_fake))
    assert -EPS <= m["autossuficiencia"] <= 1.0 + EPS
    assert -EPS <= m["autoconsumo"] <= 1.0 + EPS


def test_historico_vazio_retorna_dict_vazio():
    assert metricas_dia([]) == {}


# ── Invariantes das definições (P3) ────────────────────────────────────

def test_autossuficiencia_bate_com_fontes_locais(dia_fake, tarifa_fake):
    """Autossuficiência = (fonte_geração + fonte_bateria) / consumo."""
    hist = _rodar(dia_fake, tarifa_fake)
    m = metricas_dia(hist)
    local = sum(h["fonte_geracao_kwh"] + h["fonte_bateria_kwh"] for h in hist)
    consumo = sum(h["consumo_kw"] for h in hist)
    assert m["autossuficiencia"] == pytest.approx(local / consumo, abs=1e-9)


def test_pico_demanda_e_o_maximo_da_importacao(dia_fake, tarifa_fake):
    hist = _rodar(dia_fake, tarifa_fake)
    m = metricas_dia(hist)
    assert m["pico_demanda_kw"] == pytest.approx(max(h["importacao"] for h in hist))


def test_energia_importada_e_a_soma(dia_fake, tarifa_fake):
    hist = _rodar(dia_fake, tarifa_fake)
    m = metricas_dia(hist)
    assert m["energia_importada"] == pytest.approx(sum(h["importacao"] for h in hist))


def test_ciclos_bateria_zero_quando_bateria_parada(dia_fake, tarifa_fake):
    """Política 'manter' (a_arm=1) nunca move a bateria → 0 ciclos."""
    m = metricas_dia(_rodar(dia_fake, tarifa_fake, a_arm=1))
    assert m["ciclos_bateria"] == pytest.approx(0.0, abs=1e-9)


def test_gap_otimalidade_sinal_e_zero():
    assert gap_otimalidade(90.0, 100.0) == pytest.approx(-0.10)   # melhor que ref
    assert gap_otimalidade(110.0, 100.0) == pytest.approx(0.10)   # pior que ref
    assert gap_otimalidade(100.0, 0.0) == 0.0                     # ref nula → 0


# ── Sobre os dados reais (todas as métricas físicas plausíveis) ────────

def test_metricas_reais_sao_plausiveis(dados_reais):
    dias, tarifa = dados_reais
    for rodar in (rodar_sem_agente, rodar_heuristico):
        res = resumo_metricas([rodar(d, tarifa) for d in dias])
        assert 0.0 <= res["autossuficiencia"] <= 1.0
        assert 0.0 <= res["autoconsumo"] <= 1.0
        assert res["pico_demanda_kw"] >= 0.0
        assert res["energia_importada"] >= 0.0
        assert res["custo_total_r"] >= 0.0


def test_serie_por_dia_tem_um_valor_por_dia(dados_reais):
    dias, tarifa = dados_reais
    serie = serie_por_dia([rodar_heuristico(d, tarifa) for d in dias], "custo_total_r")
    assert len(serie) == len(dias)
    assert all(np.isfinite(x) for x in serie)
