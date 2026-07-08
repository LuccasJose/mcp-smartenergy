"""Bloco T2 — verificação do treinamento Q-learning (sem itens de seed).

Cobre:
  T2.1  Cobertura do espaço de estados (fração visitada).
  T2.2  Sanidade: política treinada supera a aleatória.
  T2.3  Convergência: a curva de treino estabiliza (critério objetivo).
"""

import copy

import numpy as np
import pytest

from smarty_energy.config import CONFIG
from smarty_energy.agents import construir_agentes
from smarty_energy.environment import ESPACO_ESTADOS_TOTAL, FazendaEnergyEnv
from smarty_energy.evaluation import cobertura_estados, rodar_rl, resumo_mes
from smarty_energy.training import treinar, metricas_convergencia


# ── T2.1 — Cobertura do espaço de estados ──────────────────────────────

def test_espaco_estados_total_confere():
    """O total combinatório deve ser 4·10·3·3·2·3 = 2160 (fonte única)."""
    assert ESPACO_ESTADOS_TOTAL == 2160


def test_cobertura_estados_reportada(agentes_treinados):
    """A cobertura deve ser reportável e estar em (0, 1].

    O valor em si é o dado que motiva a camada de julgamento: quanto MENOR a
    cobertura, mais estados o RL nunca viu — logo mais espaço para um verificador
    agir. Aqui apenas garantimos que a métrica é bem-formada e imprimimos o valor.
    """
    cob = cobertura_estados(agentes_treinados)
    print(f"\n  Cobertura do espaço de estados: {cob['visitados']}/{cob['total']} "
          f"= {cob['fracao']*100:.1f}%")
    assert cob["total"] == ESPACO_ESTADOS_TOTAL
    assert 0 < cob["visitados"] <= cob["total"]
    assert 0.0 < cob["fracao"] <= 1.0


# ── T2.2 — Sanidade: RL supera a política aleatória ────────────────────

def _rodar_aleatorio(dias, tarifa, seed=7):
    """Roda uma política totalmente aleatória em todos os dias (determinística)."""
    np.random.seed(seed)
    hists = []
    for dia in dias:
        env = FazendaEnergyEnv(dia, tarifa, CONFIG)
        env.reset()
        for _ in range(24):
            env.step(int(np.random.randint(3)), int(np.random.randint(8)),
                     int(np.random.randint(3)))
        hists.append(env.historico)
    return hists


def test_rl_supera_politica_aleatoria(dados_reais, agentes_treinados):
    """T2.2: se o RL não superar o acaso, há erro de formulação do problema."""
    dias, tarifa = dados_reais
    custo_rl = resumo_mes([rodar_rl(d, tarifa, agentes_treinados) for d in dias])[0]
    custo_rnd = resumo_mes(_rodar_aleatorio(dias, tarifa))[0]
    print(f"\n  Custo RL={custo_rl:.2f}  ·  aleatório={custo_rnd:.2f}  "
          f"→ RL melhor por {(custo_rnd - custo_rl) / custo_rnd * 100:.1f}%")
    assert custo_rl < custo_rnd, "RL não superou a política aleatória"


# ── T2.3 — Convergência do treino ──────────────────────────────────────

@pytest.fixture(scope="session")
def historico_treino(dados_reais):
    """Treina um run de 2000 ep e devolve o histórico (rewards/custos por ep)."""
    dias, tarifa = dados_reais
    np.random.seed(42)
    cfg = copy.deepcopy(CONFIG)
    cfg["n_episodios"] = 2000
    cfg["epsilon_decay"] = (cfg["epsilon_final"] / cfg["epsilon_inicial"]) ** (1 / 2000)
    return treinar(dias, tarifa, construir_agentes(cfg), cfg)


def test_metricas_convergencia_serie_curta_e_sintetica():
    """A função de convergência distingue série estável de série ainda em queda."""
    # Série curta demais → não declara estabilidade.
    assert metricas_convergencia([1.0, 2.0])["estavel"] is False
    # Série plana → estável (variação ~0).
    plana = metricas_convergencia([10.0] * 400)
    assert plana["estavel"] is True and plana["variacao_relativa"] < 1e-9
    # Série ainda caindo forte → não estável.
    caindo = metricas_convergencia(list(np.linspace(100.0, 10.0, 400)))
    assert caindo["estavel"] is False


def test_treino_converge(historico_treino):
    """T2.3: a curva de custo por episódio estabiliza ao fim do treino."""
    conv = metricas_convergencia(historico_treino["custos"])
    print(f"\n  Convergência (custo): variação entre janelas finais = "
          f"{conv['variacao_relativa']*100:.2f}%  ·  estável={conv['estavel']}")
    assert conv["estavel"], (
        f"Treino não estabilizou: variação {conv['variacao_relativa']*100:.2f}%")
