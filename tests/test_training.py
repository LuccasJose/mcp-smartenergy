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
    """O total combinatório deve ser 7·10·3·3·2·3 = 3780 (fonte única)."""
    assert ESPACO_ESTADOS_TOTAL == 3780


def test_treino_curto_propaga_soc(dia_fake, tarifa_fake):
    cfg = dict(CONFIG, n_episodios=3, epsilon_inicial=0.0, epsilon_final=0.0)
    dia = dia_fake.assign(solar_kw=50.0)
    ambientes = []
    inicios = []

    class AmbienteObservado(FazendaEnergyEnv):
        def reset(self, soc_inicial=None):
            estado = super().reset(soc_inicial)
            if soc_inicial is not None:
                ambientes.append(self)
                inicios.append(estado["soc"])
            return estado

    historico = treinar(
        [dia, dia.copy()], tarifa_fake, construir_agentes(cfg), cfg,
        env_cls=AmbienteObservado, eval_greedy_cada=0,
    )

    assert len(ambientes) == 3
    assert ambientes[0].soc > cfg["soc_inicial_pct"]
    assert inicios == pytest.approx([
        cfg["soc_inicial_pct"], ambientes[0].soc, ambientes[1].soc,
    ])
    assert historico["soc_final_pct"] == pytest.approx(ambientes[-1].soc)
    assert historico["n_episodios"] == 3


def test_treino_completa_horizonte_e_restaura_checkpoint(monkeypatch, dia_fake, tarifa_fake):
    cfg = dict(CONFIG, n_episodios=3, epsilon_inicial=0.0, epsilon_final=0.0)
    agentes = construir_agentes(cfg)
    custos = iter([1.0, 3.0, 5.0, 5.0])
    snapshots = []

    def avaliar_sintetico(*args, **kwargs):
        assert kwargs["propagar_soc"] is True
        snapshots.append({
            nome: {estado: valores.copy() for estado, valores in agente.q_table.items()}
            for nome, agente in agentes.items()
        })
        return {"custo_medio_dia_rs": next(custos)}

    monkeypatch.setattr("smarty_energy.training.avaliar_politica", avaliar_sintetico)
    historico = treinar([dia_fake], tarifa_fake, agentes, cfg, eval_greedy_cada=1)

    assert len(historico["custos"]) == historico["n_episodios"] == 3
    assert historico["best_ep"] == 1
    assert historico["best_custo_med"] == 1.0
    assert historico["custo_greedy_ultimo_ep"] == 5.0
    assert historico["curva_greedy"] == [(1, 1.0), (2, 3.0), (3, 5.0)]
    assert len(snapshots) == 4
    for nome, agente in agentes.items():
        assert agente.n_updates == 72
        assert set(agente.q_table) == set(snapshots[0][nome])
        for estado, esperado in snapshots[0][nome].items():
            np.testing.assert_array_equal(agente.q_table[estado], esperado)


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
    """Treina um run de 3000 ep e devolve o histórico (rewards/custos por ep).

    2000 ep bastavam com 3 ações de bateria; com o espaço ampliado (6 ações)
    e o rescue do pivô, a curva só estabiliza (<5%) a partir de ~3000 ep.
    """
    dias, tarifa = dados_reais
    np.random.seed(42)
    cfg = copy.deepcopy(CONFIG)
    cfg["n_episodios"] = 3000
    cfg["epsilon_decay"] = (cfg["epsilon_final"] / cfg["epsilon_inicial"]) ** (1 / 3000)
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
