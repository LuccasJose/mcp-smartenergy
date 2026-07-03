"""Validação das restrições rígidas (HARD) do ambiente.

Estas restrições devem valer para QUALQUER política de ações — por isso os
testes rodam sobre todos os 31 dias reais com três políticas diferentes
(heurística, aleatória e 'manter'). Se uma restrição pode ser violada por
alguma sequência de ações, ela não é realmente rígida.

Restrições verificadas:
  R-SOC      : 0 ≤ SoC ≤ 100 %
  R-PCC      : importação e exportação ≤ pcc_max_kw, sem simultaneidade
  R-BALANCO  : fonte_geração + fonte_bateria + fonte_rede = consumo
  R-TETO     : consumo ≤ teto escolhido pelo gerente
  R-THROUGHPUT: energia movimentada na bateria ≤ limite diário
  R-BOMBA    : bomba ligada exatamente no cronograma fixo
  R-PIVO     : irrigação em 0 ou 8 horas consecutivas (1 ativação/dia)
  R-SECADOR  : meta diária de energia do secador atingida
  R-SEDE     : consumo da sede dentro de ±20 % do ideal
"""

import numpy as np
import pytest

from smarty_energy.config import CONFIG, TETOS_KW, BOMBA_HORAS_ON
from smarty_energy.environment import FazendaEnergyEnv
from smarty_energy.evaluation import rodar_heuristico

EPS = 1e-6


# ── Políticas de execução ─────────────────────────────────────────────

def _rodar_manter(dia, tarifa):
    env = FazendaEnergyEnv(dia, tarifa, CONFIG)
    env.reset()
    for _ in range(24):
        env.step(a_arm=1, a_cons=0, a_ger=2)
    return env.historico


def _rodar_aleatorio(dia, tarifa):
    env = FazendaEnergyEnv(dia, tarifa, CONFIG)
    env.reset()
    for _ in range(24):
        env.step(
            a_arm=int(np.random.randint(3)),
            a_cons=int(np.random.randint(8)),
            a_ger=int(np.random.randint(3)),
        )
    return env.historico


_POLITICAS = {
    "heuristico": rodar_heuristico,
    "aleatorio" : _rodar_aleatorio,
    "manter"    : _rodar_manter,
}


@pytest.fixture(scope="session")
def execucoes(dados_reais):
    """(politica, indice_dia, dia_df, historico) para todos os dias × políticas."""
    dias, tarifa = dados_reais
    np.random.seed(123)
    out = []
    for nome, fn in _POLITICAS.items():
        for i, dia in enumerate(dias):
            out.append((nome, i, dia, fn(dia, tarifa)))
    return out


def _ids(execucoes):
    return [f"{nome}-dia{i:02d}" for (nome, i, _, _) in execucoes]


# ── R-SOC ─────────────────────────────────────────────────────────────

def test_soc_dentro_dos_limites(execucoes):
    for nome, i, _, hist in execucoes:
        for h in hist:
            assert 0.0 <= h["soc"] <= 100.0, f"SoC fora de [0,100] em {nome} dia {i}"


# ── R-PCC ─────────────────────────────────────────────────────────────

def test_pcc_respeita_limite(execucoes):
    pcc = CONFIG["pcc_max_kw"]
    for nome, i, _, hist in execucoes:
        for h in hist:
            assert h["importacao"] <= pcc + EPS, f"Importação > PCC em {nome} dia {i}"
            assert h["exportacao"] <= pcc + EPS, f"Exportação > PCC em {nome} dia {i}"


def test_importacao_exportacao_nao_simultaneas(execucoes):
    for nome, i, _, hist in execucoes:
        for h in hist:
            assert not (h["importacao"] > EPS and h["exportacao"] > EPS), \
                f"Import e export simultâneos em {nome} dia {i} hora {h['hora']}"


def test_rede_e_excedente_nao_negativos(execucoes):
    for nome, i, _, hist in execucoes:
        for h in hist:
            assert h["rede_kwh"] >= -EPS
            assert h["excedente"] >= -EPS


# ── R-BALANCO (fechamento energético das fontes) ──────────────────────

def test_fontes_somam_o_consumo(execucoes):
    for nome, i, _, hist in execucoes:
        for h in hist:
            fontes = h["fonte_geracao_kwh"] + h["fonte_bateria_kwh"] + h["fonte_rede_kwh"]
            assert fontes == pytest.approx(h["consumo_kw"], abs=1e-6), \
                f"Fontes não fecham com o consumo em {nome} dia {i} hora {h['hora']}"


# ── R-TETO ────────────────────────────────────────────────────────────

def test_consumo_respeita_teto(execucoes):
    for nome, i, _, hist in execucoes:
        for h in hist:
            teto = TETOS_KW[h["a_ger"]]
            assert h["consumo_kw"] <= teto + EPS, \
                f"Consumo acima do teto em {nome} dia {i} hora {h['hora']}"


# ── R-THROUGHPUT ──────────────────────────────────────────────────────

def test_throughput_diario_limitado(execucoes):
    lim = CONFIG["bat_throughput_max_kwh"]
    for nome, i, _, hist in execucoes:
        total = sum(h["bat_carga"] + h["bat_descarga"] for h in hist)
        assert total <= lim + 1e-3, f"Throughput diário excedido em {nome} dia {i}"


# ── R-BOMBA ───────────────────────────────────────────────────────────

def test_bomba_segue_cronograma_fixo(execucoes):
    for nome, i, _, hist in execucoes:
        for h in hist:
            agendada = h["hora"] in BOMBA_HORAS_ON
            ligada = h["captacao_kw_consumido"] > EPS
            assert ligada == agendada, \
                f"Bomba fora do cronograma em {nome} dia {i} hora {h['hora']}"


# ── R-PIVO ────────────────────────────────────────────────────────────

def test_pivo_zero_ou_oito_horas_consecutivas(execucoes):
    alvo = CONFIG["pivo_horas_alvo"]
    for nome, i, _, hist in execucoes:
        horas_on = [h["hora"] for h in hist if h["pivo_kw_consumido"] > EPS]
        if not horas_on:
            continue  # pivô nunca ativado é permitido
        assert len(horas_on) == alvo, \
            f"Pivô ligou {len(horas_on)}h (esperado 0 ou {alvo}) em {nome} dia {i}"
        # Consecutivas: primeira..última sem buracos
        assert horas_on == list(range(horas_on[0], horas_on[0] + alvo)), \
            f"Pivô não consecutivo em {nome} dia {i}: {horas_on}"


def test_pivo_ativado_ao_menos_uma_vez_no_heuristico(execucoes):
    alvo = CONFIG["pivo_horas_alvo"]
    dias_heur = [(i, hist) for (nome, i, _, hist) in execucoes if nome == "heuristico"]
    ativou_algum = any(
        sum(1 for h in hist if h["pivo_kw_consumido"] > EPS) == alvo
        for _, hist in dias_heur
    )
    assert ativou_algum, "Heurística nunca completou as 8h de irrigação em nenhum dia"


# ── R-SECADOR ─────────────────────────────────────────────────────────

def test_meta_secador_atingida(execucoes):
    meta = CONFIG["secador_meta_kwh"]
    for nome, i, _, hist in execucoes:
        total_sec = sum(h["secador_kw_consumido"] for h in hist)
        assert total_sec >= meta - 1e-3, \
            f"Meta do secador não atingida ({total_sec:.2f} < {meta}) em {nome} dia {i}"


# ── R-SEDE ────────────────────────────────────────────────────────────

def test_sede_dentro_do_desvio_maximo(execucoes):
    desvio = CONFIG["sede_desvio_max"]
    for nome, i, dia, hist in execucoes:
        for h in hist:
            ideal = float(dia.iloc[h["hora"]]["sede_kw"])
            lo, hi = ideal * (1 - desvio) - EPS, ideal * (1 + desvio) + EPS
            assert lo <= h["sede_kw_consumido"] <= hi, \
                f"Sede fora de ±{desvio:.0%} em {nome} dia {i} hora {h['hora']}"
