"""Testes básicos do ambiente, agentes e carregamento de dados."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Garante que src/ está no path mesmo sem instalar o pacote
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smarty_energy.config import CONFIG, TETOS_KW
from smarty_energy.environment import FazendaEnergyEnv
from smarty_energy.agents import AgenteQL, AgentesHeuristicos


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tarifa_fake() -> np.ndarray:
    """Tarifa constante de R$0,70 com pico de R$1,10 das 18h às 20h."""
    t = np.full(24, 0.70)
    t[18:21] = 1.10
    return t


@pytest.fixture
def dia_fake() -> pd.DataFrame:
    """Dia sintético com geração e consumo constantes."""
    df = pd.DataFrame({
        "hora"       : range(24),
        "solar_kw"   : [10.0] * 24,
        "eolico_kw"  : [2.0]  * 24,
        "pivo_kw"    : [5.0]  * 24,
        "captacao_kw": [3.0]  * 24,
        "sede_kw"    : [1.0]  * 24,
        "silo_kw"    : [0.5]  * 24,
        "data"       : pd.Timestamp("2025-01-01"),
    })
    return df


@pytest.fixture
def env(dia_fake, tarifa_fake) -> FazendaEnergyEnv:
    return FazendaEnergyEnv(dia_fake, tarifa_fake, CONFIG)


# ── Testes do Ambiente ─────────────────────────────────────────────────────────

def test_env_reset_retorna_estado_valido(env):
    estado = env.reset()
    assert "hora"      in estado
    assert "soc"       in estado
    assert "solar_kw"  in estado
    assert "tarifa"    in estado
    assert estado["hora"] == 0
    assert estado["soc"]  == CONFIG["soc_inicial_pct"]


def test_env_step_retorna_tupla_correta(env):
    env.reset()
    prox, reward, done, info = env.step(1, 0, 2)
    assert isinstance(prox,   dict)
    assert isinstance(reward, float)
    assert isinstance(done,   bool)
    assert "custo"    in info
    assert "rede_kwh" in info
    assert done is False


def test_env_episodio_completo(env):
    env.reset()
    done = False
    passos = 0
    while not done:
        _, _, done, _ = env.step(1, 0, 1)
        passos += 1
    assert passos == 24
    assert len(env.historico) == 24


def test_env_discretizar_retorna_tupla_de_4(env):
    estado = env.reset()
    disc = env.discretizar(estado)
    assert isinstance(disc, tuple)
    assert len(disc) == 4
    h, s, g, t = disc
    assert 0 <= h <= 3
    assert 0 <= s <= 4
    assert g in (0, 1, 2)
    assert t in (0, 1)


def test_env_soc_nunca_ultrapassa_limites(env):
    env.reset()
    done = False
    while not done:
        _, _, done, _ = env.step(0, 0, 2)  # sempre carrega
    socs = [h["soc"] for h in env.historico]
    assert all(0.0 <= soc <= 100.0 for soc in socs)


# ── Testes dos Agentes ─────────────────────────────────────────────────────────

def test_agente_ql_acao_valida():
    agente = AgenteQL(3, "Teste", CONFIG)
    for _ in range(20):
        acao = agente.agir((0, 2, 1, 0), explorando=True)
        assert acao in (0, 1, 2)


def test_agente_ql_greedy_apos_aprendizado():
    agente = AgenteQL(3, "Teste", CONFIG)
    estado = (0, 2, 1, 0)
    agente.aprender(estado, 1, 5.0, estado, False)
    acao = agente.agir(estado, explorando=False)
    assert acao == 1  # ação 1 deve ter maior Q-value


def test_agente_ql_decaimento_epsilon():
    agente = AgenteQL(3, "Teste", CONFIG)
    eps_inicial = agente.epsilon
    agente.decair_epsilon()
    assert agente.epsilon < eps_inicial
    assert agente.epsilon >= CONFIG["epsilon_final"]


def test_agente_ql_save_load(tmp_path):
    agente = AgenteQL(3, "Teste", CONFIG)
    estado = (1, 3, 2, 1)
    agente.aprender(estado, 0, 2.0, estado, False)
    path = tmp_path / "qtable.pkl"
    agente.save(path)
    agente2 = AgenteQL(3, "Teste", CONFIG)
    agente2.load(path)
    assert agente2.n_estados > 0
    assert agente2.q_table[estado][0] == agente.q_table[estado][0]


def test_heuristica_retorna_acoes_validas(dia_fake, tarifa_fake):
    h = AgentesHeuristicos()
    estado = {"hora": 0, "soc": 50.0, "solar_kw": 8.0, "eolico_kw": 2.0, "tarifa": 0.70}
    stress = h.stress_financeiro(estado)
    assert 0.0 <= stress <= 100.0
    assert h.armazenamento(estado) in (0, 1, 2)
    assert h.consumo(estado, stress) in (0, 1, 2, 3)
    assert h.gerente(estado, stress) in (0, 1, 2)


# ── Testes de Configuração ─────────────────────────────────────────────────────

def test_config_chaves_obrigatorias():
    chaves = [
        "n_episodios", "alpha", "gamma", "epsilon_inicial", "epsilon_final",
        "epsilon_decay", "bateria_cap_kwh", "soc_inicial_pct", "soc_min_pct",
        "soc_max_pct", "eficiencia_carga", "eficiencia_descarga",
        "bat_throughput_max_kwh", "pcc_max_kw", "inversor_fv_max_kw",
        "eolico_nominal_kw", "w_custo", "pen_soc", "pen_teto",
        "pen_producao", "pen_pcc", "bonus_excedente", "bonus_soc_ok",
    ]
    for chave in chaves:
        assert chave in CONFIG, f"Chave ausente em CONFIG: {chave}"


def test_tetos_kw_valores():
    assert TETOS_KW[0] < TETOS_KW[1] < TETOS_KW[2]
