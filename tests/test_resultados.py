"""Testes de integração — valida os resultados/números do TCC.

Treina os agentes (nº de episódios configurável via `SMARTY_TEST_EPISODIOS`)
e compara RL contra os baselines 'Sem Agente' e 'Heurístico' em todos os
dias reais, verificando as alegações centrais do trabalho:

  * RL não gera violações de SoC (segurança operacional).
  * RL economiza em relação a operar 'sem agente'.
  * RL reduz a dependência da rede elétrica.
  * Resultado é reprodutível para a mesma semente.

Execução rápida (padrão, ~800 episódios):
    pytest tests/test_resultados.py -s

Execução completa (fiel ao TCC):
    $env:SMARTY_TEST_EPISODIOS = "100000"
    $env:SMARTY_MIN_ECONOMIA_PCT = "40"
    pytest tests/test_resultados.py -s
"""

import os

import numpy as np
import pytest

from smarty_energy.evaluation import (
    rodar_sem_agente,
    rodar_heuristico,
    rodar_rl,
    resumo_mes,
)
from smarty_energy.benchmark import comparar_metrica_pareada


def _min_economia_pct() -> float:
    """Economia mínima exigida do RL vs 'sem agente' (%). Padrão: 0."""
    try:
        return float(os.getenv("SMARTY_MIN_ECONOMIA_PCT", "0"))
    except ValueError:
        return 0.0


@pytest.fixture(scope="session")
def avaliacao(dados_reais, agentes_treinados, n_ep_teste):
    """Roda os três cenários em todos os dias e resume as métricas."""
    dias, tarifa = dados_reais
    res_s = [rodar_sem_agente(d, tarifa) for d in dias]
    res_h = [rodar_heuristico(d, tarifa) for d in dias]
    res_r = [rodar_rl(d, tarifa, agentes_treinados) for d in dias]

    cs, rs, vs, rws = resumo_mes(res_s)
    ch, rh, vh, rwh = resumo_mes(res_h)
    cr, rr, vr, rwr = resumo_mes(res_r)

    metr = {
        "sem":  {"custo": cs, "rede": rs, "viol": vs, "reward": rws},
        "heur": {"custo": ch, "rede": rh, "viol": vh, "reward": rwh},
        "rl":   {"custo": cr, "rede": rr, "viol": vr, "reward": rwr},
    }

    econ_custo = (cs - cr) / cs * 100 if cs else 0.0
    econ_rede = (rs - rr) / rs * 100 if rs else 0.0

    print("\n" + "=" * 68)
    print(f"AVALIAÇÃO — {n_ep_teste} episódios de treino")
    print("=" * 68)
    print(f"  {'Métrica':<22}{'Sem Agente':>13}{'Heurístico':>13}{'RL':>13}")
    print(f"  {'Custo (R$/dia)':<22}{cs:>13.2f}{ch:>13.2f}{cr:>13.2f}")
    print(f"  {'Rede (kWh/dia)':<22}{rs:>13.2f}{rh:>13.2f}{rr:>13.2f}")
    print(f"  {'Violações SoC/dia':<22}{vs:>13.2f}{vh:>13.2f}{vr:>13.2f}")
    print(f"  {'Reward/dia':<22}{rws:>13.2f}{rwh:>13.2f}{rwr:>13.2f}")
    print("-" * 68)
    print(f"  Economia de custo (RL vs Sem Agente): {econ_custo:+.1f} %")
    print(f"  Redução de rede   (RL vs Sem Agente): {econ_rede:+.1f} %")
    print("=" * 68)

    metr["economia_custo_pct"] = econ_custo
    metr["reducao_rede_pct"] = econ_rede
    return metr


def test_rl_sem_violacoes_soc(avaliacao):
    """Alegação do TCC: zero violações de segurança operacional (SoC)."""
    assert avaliacao["rl"]["viol"] == 0.0, \
        f"RL teve {avaliacao['rl']['viol']:.2f} violações de SoC/dia"


def test_rl_economiza_vs_sem_agente(avaliacao):
    """RL deve custar menos do que operar sem gestão."""
    minimo = _min_economia_pct()
    econ = avaliacao["economia_custo_pct"]
    assert econ >= minimo, \
        f"Economia do RL ({econ:.1f}%) abaixo do mínimo exigido ({minimo:.1f}%)"


def test_rl_reduz_dependencia_da_rede(avaliacao):
    """RL deve importar menos energia da rede do que 'sem agente'."""
    assert avaliacao["reducao_rede_pct"] >= 0.0, \
        f"RL não reduziu a dependência da rede ({avaliacao['reducao_rede_pct']:.1f}%)"


def test_custo_rl_finito_e_positivo(avaliacao):
    cr = avaliacao["rl"]["custo"]
    assert np.isfinite(cr) and cr >= 0.0


# ── T3.2 — Comparação estatística pareada (RL × baselines) ─────────────

@pytest.fixture(scope="session")
def historicos_por_config(dados_reais, agentes_treinados):
    """Históricos diários (31 dias) de cada configuração — insumo do pareado."""
    dias, tarifa = dados_reais
    return {
        "sem": [rodar_sem_agente(d, tarifa) for d in dias],
        "heur": [rodar_heuristico(d, tarifa) for d in dias],
        "rl":  [rodar_rl(d, tarifa, agentes_treinados) for d in dias],
    }


def _reportar(nome: str, w: dict) -> None:
    print(f"\n  [{nome}] métrica={w['metrica']}  "
          f"média_RL={w['media_a']:.2f}  média_base={w['media_b']:.2f}  "
          f"Δ={w['delta_medio']:+.2f}  z={w['z']:.2f}  p={w['p_valor']:.4f}  "
          f"r={w['r']:.3f}  (n={w['n_efetivo']})")


def test_pareado_rl_vs_sem_agente_custo(historicos_por_config):
    """T3: RL não deve custar mais que C0 (sem agente), pareado por dia.

    Reporta p-valor e tamanho de efeito (r). A significância forte é esperada
    no treino completo (100k ep); aqui garantimos a direção e a boa-formação
    da estatística.
    """
    w = comparar_metrica_pareada(
        historicos_por_config["rl"], historicos_por_config["sem"], "custo_total_r")
    _reportar("RL vs C0", w)
    assert w["delta_medio"] <= 1e-6, "RL custou mais que 'sem agente' na média"
    assert 0.0 <= w["p_valor"] <= 1.0 and w["r"] >= 0.0


def test_pareado_rl_vs_heuristico_bem_formado(historicos_por_config):
    """T3: a comparação RL × C1 (heurístico) produz estatística válida.

    Sem asserção de significância (depende da duração do treino) — o valor é
    reportado para o Capítulo 5; aqui validamos a máquina de comparação.
    """
    w = comparar_metrica_pareada(
        historicos_por_config["rl"], historicos_por_config["heur"], "custo_total_r")
    _reportar("RL vs C1", w)
    assert w["n_efetivo"] >= 0
    assert 0.0 <= w["p_valor"] <= 1.0
    assert w["metrica"] == "custo_total_r"


def test_pareado_funciona_para_autossuficiencia(historicos_por_config):
    """A comparação pareada vale para qualquer métrica 4.1, não só custo."""
    w = comparar_metrica_pareada(
        historicos_por_config["rl"], historicos_por_config["sem"], "autossuficiencia")
    _reportar("RL vs C0", w)
    assert w["metrica"] == "autossuficiencia"
    assert 0.0 <= w["p_valor"] <= 1.0


@pytest.mark.slow
def test_reprodutibilidade_mesma_semente(dados_reais, treino_fn, seed_teste):
    """Mesma semente → mesmo resultado de avaliação (determinismo)."""
    dias, tarifa = dados_reais
    n_ep = 120  # curto: só precisa comparar dois treinos idênticos

    ag1 = treino_fn(dias, tarifa, n_ep, seed=seed_teste)
    ag2 = treino_fn(dias, tarifa, n_ep, seed=seed_teste)

    c1 = resumo_mes([rodar_rl(d, tarifa, ag1) for d in dias])[0]
    c2 = resumo_mes([rodar_rl(d, tarifa, ag2) for d in dias])[0]

    assert c1 == pytest.approx(c2, rel=1e-9), \
        f"Treinos com mesma semente divergiram: {c1} != {c2}"
