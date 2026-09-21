"""AgenteQL (hysteretic) e IQLSystem."""

import os
import pickle
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from smarty_energy.agents import AgenteQL, IQLSystem, construir_agentes
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

def test_topologia_publica_e_config_compartilhada(cfg):
    agentes = construir_agentes(cfg)
    assert list(agentes) == ["armazenamento", "consumo", "gerente"]
    assert [agente.n_acoes for agente in agentes.values()] == [6, 8, 3]
    assert [agente.nome for agente in agentes.values()] == list(agentes)
    assert all(agente.cfg is cfg for agente in agentes.values())
    sistema = IQLSystem(cfg)
    assert sistema.cfg is not cfg
    assert sistema.cfg == cfg
    assert all(agente.cfg is sistema.cfg for agente in sistema.agentes.values())


def test_api_publica_reexporta_as_mesmas_implementacoes():
    import smarty_energy
    from smarty_energy import agents, training
    from smarty_energy.agents import evaluation, q_learning, rules, system

    esperados = {
        "AgenteQL": q_learning.AgenteQL,
        "construir_agentes": q_learning.construir_agentes,
        "AgenteFinanceiro": rules.AgenteFinanceiro,
        "AgentesHeuristicos": rules.AgentesHeuristicos,
        "SemAgente": rules.SemAgente,
        "avaliar_politica": evaluation.avaliar_politica,
        "IQLSystem": system.IQLSystem,
    }
    assert set(agents.__all__) == set(esperados)
    for nome, objeto in esperados.items():
        assert getattr(agents, nome) is objeto
        if nome in smarty_energy.__all__:
            assert getattr(smarty_energy, nome) is objeto
        assert pickle.loads(pickle.dumps(objeto)) is objeto
        referencia_legada = f"csmarty_energy.agents\n{nome}\n.".encode("ascii")
        assert pickle.loads(referencia_legada) is objeto
    assert rules.avaliar_politica is system.avaliar_politica is training.avaliar_politica
    assert system.construir_agentes is q_learning.construir_agentes


@pytest.mark.parametrize("modulo", [
    "smarty_energy.environment", "smarty_energy.training", "smarty_energy.agents.system",
])
def test_importacao_em_processo_novo_sem_ciclo(modulo):
    raiz = Path(__file__).resolve().parents[2]
    ambiente = dict(os.environ, PYTHONPATH=str(raiz / "src"), PYTHON_DOTENV_DISABLED="1")
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {modulo}; from smarty_energy.agents import IQLSystem; "
         "assert len(IQLSystem().agentes) == 3"],
        cwd=raiz, env=ambiente, capture_output=True, text=True, timeout=30,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


@pytest.mark.parametrize("n_dias", [5, 6])
@pytest.mark.parametrize("decay_manual", [False, True])
def test_iql_preserva_delegacao_e_selecao_legada(monkeypatch, dia_fake, tarifa_fake, cfg, n_dias, decay_manual):
    from smarty_energy import training
    from smarty_energy.config import ajustar_decay
    dias = [dia_fake.copy() for _ in range(n_dias)]
    sistema = IQLSystem(cfg)
    parametros = {"n_episodios": 2}
    if decay_manual:
        parametros["epsilon_decay"] = 0.75
    sistema.reconfigurar(parametros)
    historico = {
        "soc_final_pct": 62.0, "rewards": [1.0, 2.0], "custos": [3.0, 4.0],
        "epsilons": [0.5, 0.25], "best_ep": 1, "best_custo_med": 3.0, "duracao_s": 0.0,
    }

    def executar(recebidos, tarifa, agentes, config, **opcoes):
        assert recebidos is dias
        assert tarifa is tarifa_fake
        assert agentes is sistema.agentes
        assert config["n_episodios"] == 2
        esperado = 0.75 if decay_manual else ajustar_decay(cfg, 2)["epsilon_decay"]
        assert config["epsilon_decay"] == esperado
        assert all(agente.eps_decay == esperado for agente in agentes.values())
        selecionados = dias[::3] if n_dias >= 6 else dias
        assert [id(dia) for dia in opcoes["dias_selecao"]] == [id(dia) for dia in selecionados]
        assert opcoes["tracker"] is None
        return historico

    monkeypatch.setattr(training, "treinar", executar)
    resumo = sistema.treinar(dias, tarifa_fake)
    assert sistema.ultimo_hist is historico
    assert sistema.soc_propagado == 62.0
    assert resumo["episodios_treinados"] == 2
    assert resumo["best_ep"] == 1


def test_agir_preserva_rng_global_e_desempate(cfg):
    estado = (0, 5, 1, 0, 0, 1)
    agente = AgenteQL(6, cfg=dict(cfg, epsilon_inicial=1.0))
    anterior = np.random.get_state()
    try:
        np.random.seed(42)
        esperado = []
        for _ in range(12):
            np.random.random()
            esperado.append(np.random.randint(6))
        np.random.seed(42)
        assert [agente.agir(estado) for _ in range(12)] == esperado
        assert agente.n_estados == 0
        antes_greedy = np.random.get_state()
        assert agente.agir(estado, explorando=False) == 0
        assert agente.n_estados == 1
        np.testing.assert_array_equal(np.random.get_state()[1], antes_greedy[1])
        assert np.random.get_state()[2:] == antes_greedy[2:]
    finally:
        np.random.set_state(anterior)


def test_load_legado_sem_numero_de_acoes(cfg, tmp_path):
    estado = (0, 5, 1, 0, 0, 1)
    arquivo = tmp_path / "legado.pkl"
    with arquivo.open("wb") as destino:
        pickle.dump({"q_table": {estado: np.arange(6, dtype=float)}, "epsilon": 0.2}, destino)
    agente = AgenteQL(6, cfg=cfg)
    agente.load(arquivo)
    assert agente.n_acoes == 6
    assert agente.epsilon == 0.2
    assert agente.n_updates == 0
    np.testing.assert_array_equal(agente.q_table[estado], np.arange(6, dtype=float))
    np.testing.assert_array_equal(agente.q_table[(1, 5, 1, 0, 0, 1)], np.zeros(6))


def test_iql_reconfigurar_reset_e_persistencia(cfg, tmp_path):
    sistema = IQLSystem(cfg)
    estado = (0, 5, 1, 0, 0, 1)
    sistema.aprender_todos(estado, (0, 1, 2), 10.0, estado, True)
    tabelas = {nome: agente.q_table[estado].copy() for nome, agente in sistema.agentes.items()}
    sistema.reconfigurar({"alpha": 0.3, "beta": 0.02, "n_episodios": 2, "epsilon_decay": 0.8})
    assert sistema.decay_manual is True
    assert sistema.n_episodios == 2
    for nome, agente in sistema.agentes.items():
        assert (agente.alpha, agente.beta, agente.eps_decay) == (0.3, 0.02, 0.8)
        np.testing.assert_array_equal(agente.q_table[estado], tabelas[nome])
    sistema.save_all(tmp_path)
    restaurado = IQLSystem(cfg)
    restaurado.load_all(tmp_path)
    for nome, agente in restaurado.agentes.items():
        np.testing.assert_array_equal(agente.q_table[estado], tabelas[nome])
        assert agente.n_updates == 1
    sistema.reset_qtables()
    assert all(agente.n_estados == agente.n_updates == 0 for agente in sistema.agentes.values())
    assert all(agente.td_errors == [] for agente in sistema.agentes.values())
    assert all(agente.epsilon == sistema.cfg["epsilon_inicial"] for agente in sistema.agentes.values())

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
