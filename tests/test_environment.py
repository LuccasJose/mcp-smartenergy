"""Testes básicos do ambiente, agentes e configuração.

Fixtures compartilhadas (`env`, `dia_fake`, `tarifa_fake`) vêm de conftest.py.
"""

import numpy as np
import pytest

from smarty_energy.config import CONFIG, TETOS_KW
from smarty_energy.agents import AgenteQL, AgentesHeuristicos


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
    # `info` é o registro horário completo — o mesmo dict apendado no histórico.
    assert "custo_r"  in info
    assert "rede_kwh" in info
    assert info is env.historico[-1]
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


def test_env_discretizar_retorna_tupla_de_6(env):
    estado = env.reset()
    disc = env.discretizar(estado)
    assert isinstance(disc, tuple)
    assert len(disc) == 6
    h, s, g, st, meta, b = disc
    assert 0 <= h <= 6          # bucket temporal
    assert 0 <= s <= 9          # bucket soc (10 buckets)
    assert g in (0, 1, 2)       # bucket solar
    assert st in (0, 1, 2)      # bucket estresse
    assert meta in (0, 1)       # meta secador
    assert b in (0, 1, 2)       # progresso bomba


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
    assert h.armazenamento(estado) in (0, 1, 2, 3, 4)
    assert h.consumo(estado, stress) in range(8)
    assert h.gerente(estado, stress) in (0, 1, 2)


# ── Testes de Configuração ─────────────────────────────────────────────────────

def test_config_chaves_obrigatorias():
    chaves = [
        # Treino
        "n_episodios", "alpha", "gamma", "epsilon_inicial", "epsilon_final",
        "epsilon_decay",
        # Bateria
        "bateria_cap_kwh", "soc_inicial_pct", "soc_min_pct", "soc_max_pct",
        "eficiencia_carga", "eficiencia_descarga", "bat_throughput_max_kwh",
        # Conexão e geração
        "pcc_max_kw", "inversor_fv_max_kw", "eolico_nominal_kw",
        # Financeiro
        "credito_inicial_kwh", "tarifa_estresse_limiar",
        # Metas operacionais
        "pivo_horas_alvo", "pivo_nominal_kw", "bomba_cap_nominal_kw",
        "secador_meta_kwh", "secador_max_kw", "sede_desvio_max",
        # Pesos do reward
        "w_custo", "w_estresse", "w_bonus_carga", "pen_soc", "pen_teto",
        "pen_producao", "pen_pcc", "bonus_excedente", "bonus_soc_ok",
        # Penalidades operacionais e shaping
        "pen_secador_meta", "pen_sede_desvio", "pen_pivo_pico",
        "pen_secador_pico", "bonus_pivo_solar", "bonus_sec_excedente",
    ]
    for chave in chaves:
        assert chave in CONFIG, f"Chave ausente em CONFIG: {chave}"


def test_tetos_kw_valores():
    assert TETOS_KW[0] < TETOS_KW[1] < TETOS_KW[2]
