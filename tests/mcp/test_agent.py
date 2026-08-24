"""AgenteQL (hysteretic) e IQLSystem."""

import numpy as np
import pytest

from smarty_energy.agents import AgenteQL, IQLSystem
from smarty_energy.config import CONFIG


# --- AgenteQL: aprendizado --------------------------------------------------

def test_agir_devolve_acao_valida(cfg):
    ag = AgenteQL(n_acoes=8, cfg=cfg)
    s = (0, 1, 2, 0, 0, 1)
    a = ag.agir(s, explorando=False)
    assert 0 <= a < 8


def test_aprender_incrementa_n_updates(cfg):
    ag = AgenteQL(n_acoes=3, cfg=cfg)
    s, s2 = (0, 1, 0, 0, 0, 0), (0, 2, 0, 0, 0, 0)
    ag.aprender(s, 0, r=1.0, s2=s2, done=False)
    assert ag.n_updates == 1


def test_hysteretic_td_positivo_usa_alpha(cfg):
    """TD>0 → atualizacao com taxa alpha (otimista)."""
    cfg = dict(cfg, alpha=0.5, beta=0.01)
    ag = AgenteQL(n_acoes=3, cfg=cfg)
    s, s2 = (0, 1, 0, 0, 0, 0), (0, 2, 0, 0, 0, 0)
    # Q[s][0] = 0; q_alvo = 10; td = +10; novo Q = 0 + 0.5*10 = 5.0
    ag.aprender(s, 0, r=10.0, s2=s2, done=True)
    assert abs(ag.q_table[s][0] - 5.0) < 1e-9


def test_hysteretic_td_negativo_usa_beta(cfg):
    """TD<0 → atualizacao com taxa beta (pessimista, beta << alpha)."""
    cfg = dict(cfg, alpha=0.5, beta=0.01)
    ag = AgenteQL(n_acoes=3, cfg=cfg)
    s, s2 = (0, 1, 0, 0, 0, 0), (0, 2, 0, 0, 0, 0)
    # Estado inicial: Q[s][0] = +10
    ag.q_table[s][0] = 10.0
    # q_alvo = 0; td = -10; novo Q = 10 + 0.01 * (-10) = 9.9
    ag.aprender(s, 0, r=0.0, s2=s2, done=True)
    assert abs(ag.q_table[s][0] - 9.9) < 1e-9


def test_epsilon_decay(cfg):
    cfg = dict(cfg, epsilon_inicial=1.0, epsilon_final=0.1, epsilon_decay=0.9)
    ag = AgenteQL(n_acoes=3, cfg=cfg)
    eps0 = ag.epsilon
    ag.decair_epsilon()
    assert ag.epsilon < eps0
    assert abs(ag.epsilon - 0.9) < 1e-9
    # Nao desce abaixo do epsilon_final
    for _ in range(200):
        ag.decair_epsilon()
    assert ag.epsilon == cfg["epsilon_final"]


def test_td_errors_janela_rolante(cfg):
    """Janela rolante de td_errors limita o tamanho."""
    ag = AgenteQL(n_acoes=3, cfg=cfg)
    ag.td_errors_max_len = 10
    s, s2 = (0, 0, 0, 0, 0, 0), (0, 1, 0, 0, 0, 0)
    for i in range(50):
        ag.aprender(s, 0, r=float(i), s2=s2, done=False)
    assert len(ag.td_errors) == 10


def test_save_load_preserva_qtable(cfg, tmp_path):
    ag = AgenteQL(n_acoes=3, nome="armazenamento", cfg=cfg)
    s = (0, 5, 1, 0, 0, 1)
    ag.q_table[s] = np.array([1.0, 2.0, 3.0])
    ag.n_updates = 42

    path = tmp_path / "qtable.pkl"
    ag.save(path)

    ag2 = AgenteQL(n_acoes=3, nome="armazenamento", cfg=cfg)
    ag2.load(path)
    assert ag2.n_updates == 42
    assert np.allclose(ag2.q_table[s], [1.0, 2.0, 3.0])


# --- IQLSystem --------------------------------------------------------------

def test_iqlsystem_cria_3_agentes(iql):
    assert set(iql.agentes.keys()) == {"armazenamento", "consumo", "gerente"}
    assert iql.agentes["armazenamento"].n_acoes == 6
    assert iql.agentes["consumo"].n_acoes == 8
    assert iql.agentes["gerente"].n_acoes == 3


def test_iqlsystem_treinar_propaga_soc(dia_fake, tarifa_fake, cfg):
    """SOC final do ep N vira inicial do ep N+1."""
    from smarty_energy.environment import FazendaEnergyEnv
    cfg = dict(cfg, n_episodios=2, epsilon_inicial=0.0)  # determinismo
    iql = IQLSystem(cfg)
    sumario = iql.treinar([dia_fake], tarifa_fake, FazendaEnergyEnv)
    assert sumario["episodios_treinados"] == 2
    # soc_propagado deve ser uma fracao valida
    assert 0.0 <= iql.soc_propagado <= 100.0
