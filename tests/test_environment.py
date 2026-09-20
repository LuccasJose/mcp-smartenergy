"""Testes básicos do ambiente, agentes e configuração.

Fixtures compartilhadas (`env`, `dia_fake`, `tarifa_fake`) vêm de conftest.py.
"""

from unittest.mock import Mock

import numpy as np
import pytest

from smarty_energy import evaluation
from smarty_energy.config import (
    ACAO_CARREGAR_REDE, CONFIG, FRACOES_DESCARGA, TETOS_KW,
    N_ACOES_ARMAZENAMENTO, N_ACOES_CONSUMO, N_ACOES_GERENTE,
)
from smarty_energy.agents import AgenteQL, AgentesHeuristicos
from smarty_energy.environment import (
    BUCKETS_ESTADO, ESPACO_ESTADOS_TOTAL, STATE_ENCODING_VERSION, FazendaEnergyEnv,
)
from smarty_energy.evaluation import _rodar_mes


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


def test_env_reset_preserva_soc_e_reinicia_contadores(env):
    for _ in range(24):
        env.step(ACAO_CARREGAR_REDE, 0, 2)
    soc_final = env.soc
    assert env.bat_throughput_dia > 0.0
    assert env.secador_kwh_ac > 0.0
    assert env.bomba_total_h > 0
    assert env.pivo_ativado_hoje

    estado = env.reset(soc_inicial=soc_final)

    assert estado["soc"] == pytest.approx(soc_final)
    assert env.battery.soc_pct == pytest.approx(soc_final)
    assert env.hora == 0
    assert env.historico == []
    assert env.bat_throughput_dia == env.battery.throughput_kwh == 0.0
    assert env.secador_kwh_ac == 0.0
    assert env.bomba_total_h == env.pivo_lock == 0
    assert env.pivo_ativado_hoje is False
    assert env.pico_importacao_dia == 0.0


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


@pytest.mark.parametrize("campo, valor, indice, esperado", [
    ("hora", 0, 0, 0),
    ("hora", 5, 0, 0),
    ("hora", 6, 0, 1),
    ("hora", 11, 0, 1),
    ("hora", 12, 0, 2),
    ("hora", 15, 0, 2),
    ("hora", 16, 0, 3),
    ("hora", 17, 0, 3),
    ("hora", 18, 0, 4),
    ("hora", 19, 0, 4),
    ("hora", 20, 0, 5),
    ("hora", 21, 0, 6),
    ("hora", 23, 0, 6),
    ("soc", 0.0, 1, 0),
    ("soc", 9.99, 1, 0),
    ("soc", 10.0, 1, 1),
    ("soc", 89.99, 1, 8),
    ("soc", 90.0, 1, 9),
    ("soc", 100.0, 1, 9),
    ("solar_kw", 4.99, 2, 0),
    ("solar_kw", 5.0, 2, 1),
    ("solar_kw", 14.99, 2, 1),
    ("solar_kw", 15.0, 2, 2),
    ("stress", 29.99, 3, 0),
    ("stress", 30.0, 3, 1),
    ("stress", 69.99, 3, 1),
    ("stress", 70.0, 3, 2),
    ("bomba_h", 2, 5, 0),
    ("bomba_h", 3, 5, 1),
    ("bomba_h", 5, 5, 1),
    ("bomba_h", 6, 5, 2),
])
def test_env_discretizacao_limites(env, campo, valor, indice, esperado):
    estado = env.reset()
    estado[campo] = valor
    assert env.discretizar(estado)[indice] == esperado


@pytest.mark.parametrize("delta, esperado", [(-0.01, 0), (0.0, 1), (0.01, 1)])
def test_env_discretizacao_meta_secador(env, delta, esperado):
    estado = env.reset()
    estado["sec_ac"] = env.cfg["secador_meta_kwh"] + delta
    assert env.discretizar(estado)[4] == esperado


def test_env_contrato_estados_e_acoes():
    assert STATE_ENCODING_VERSION == 2
    assert BUCKETS_ESTADO == (7, 10, 3, 3, 2, 3)
    assert ESPACO_ESTADOS_TOTAL == 3780
    assert (N_ACOES_ARMAZENAMENTO, N_ACOES_CONSUMO, N_ACOES_GERENTE) == (6, 8, 3)
    assert ACAO_CARREGAR_REDE == 5
    assert FRACOES_DESCARGA == {2: 0.25, 3: 0.50, 4: 1.0}
    assert TETOS_KW == {0: 20.0, 1: 30.0, 2: 40.0}


@pytest.mark.parametrize("propagar_soc", [True, False])
def test_avaliacao_mensal_encadeia_soc_na_ordem(propagar_soc):
    dias = [object(), object(), object()]
    finais = [62.5, 27.0, 74.0]
    chamadas = []

    def rodar_dia(dia, soc_inicial):
        chamadas.append((dia, soc_inicial))
        return [{"soc": finais[len(chamadas) - 1]}]

    historicos = _rodar_mes(dias, rodar_dia, propagar_soc)

    esperados = [CONFIG["soc_inicial_pct"], 62.5, 27.0] if propagar_soc else [None] * 3
    assert chamadas == list(zip(dias, esperados))
    assert historicos == [[{"soc": final}] for final in finais]


@pytest.mark.parametrize("estrategia", ["sem_agente", "heuristico", "rl", "llm"])
@pytest.mark.parametrize("propagar_soc", [None, True, False])
def test_avaliacao_mensal_publica_preserva_argumentos(monkeypatch, estrategia, propagar_soc):
    dias = [object(), object(), object()]
    tarifa = object()
    extras = (object(),) if estrategia in ("rl", "llm") else ()
    finais = [62.5, 27.0, 74.0]
    chamadas = []

    def rodar_dia(*argumentos):
        chamadas.append(argumentos)
        return [{"soc": finais[len(chamadas) - 1]}]

    monkeypatch.setattr(evaluation, f"rodar_{estrategia}", rodar_dia)
    opcoes = {} if propagar_soc is None else {"propagar_soc": propagar_soc}

    historicos = getattr(evaluation, f"rodar_{estrategia}_mes")(
        dias, tarifa, *extras, **opcoes,
    )

    inicios = [None] * 3 if propagar_soc is False else [CONFIG["soc_inicial_pct"], 62.5, 27.0]
    assert chamadas == [
        (dia, tarifa, *extras, inicio) for dia, inicio in zip(dias, inicios)
    ]
    assert historicos == [[{"soc": final}] for final in finais]


@pytest.mark.parametrize("estrategia", ["rl", "llm"])
@pytest.mark.parametrize("propagar_soc", [True, False])
def test_avaliacao_mensal_publica_integra_bateria(dia_fake, tarifa_fake, estrategia, propagar_soc):
    if estrategia == "rl":
        decisor = {
            "armazenamento": Mock(agir=Mock(return_value=ACAO_CARREGAR_REDE)),
            "consumo": Mock(agir=Mock(return_value=0)),
            "gerente": Mock(agir=Mock(return_value=2)),
        }
    else:
        decisor = Mock(agir=Mock(return_value=(ACAO_CARREGAR_REDE, 0, 2)))

    historicos = getattr(evaluation, f"rodar_{estrategia}_mes")(
        [dia_fake, dia_fake.copy()], tarifa_fake, decisor, propagar_soc=propagar_soc,
    )

    assert [len(historico) for historico in historicos] == [24, 24]
    carga_inicial = (CONFIG["soc_max_pct"] - CONFIG["soc_inicial_pct"]) / 100.0 * CONFIG["bateria_cap_kwh"]
    assert historicos[0][0]["bat_carga"] == pytest.approx(carga_inicial)
    assert historicos[0][-1]["soc"] == pytest.approx(CONFIG["soc_max_pct"])
    assert historicos[1][0]["bat_carga"] == pytest.approx(0.0 if propagar_soc else carga_inicial)
    if estrategia == "rl":
        for agente in decisor.values():
            assert agente.agir.call_count == 48
            assert all(
                chamada.kwargs == {"explorando": False}
                for chamada in agente.agir.call_args_list
            )
    else:
        assert decisor.agir.call_count == 48
        assert all(isinstance(chamada.args[0], dict) for chamada in decisor.agir.call_args_list)


@pytest.mark.parametrize("faixa, elegivel", [
    ("abaixo", True), ("igual", False), ("acima", False),
])
def test_env_carga_rede_limiar_tarifario(dia_fake, faixa, elegivel):
    cfg = dict(CONFIG)
    limite = cfg["tarifa_referencia_arbitragem"] * (
        cfg["eficiencia_carga"] * cfg["eficiencia_descarga"]
    )
    tarifa = {
        "abaixo": np.nextafter(limite, 0.0),
        "igual": limite,
        "acima": np.nextafter(limite, np.inf),
    }[faixa]
    ambiente = FazendaEnergyEnv(
        dia_fake.assign(solar_kw=0.0, eolico_kw=0.0), np.full(24, tarifa), cfg,
    )

    _, _, _, info = ambiente.step(ACAO_CARREGAR_REDE, 0, 2)

    assert info["comando_bateria"] == "carregar_rede"
    assert info["carga_solar_ac"] == 0.0
    assert info["bat_descarga"] == 0.0
    if elegivel:
        energia_dc = (cfg["soc_max_pct"] - cfg["soc_inicial_pct"]) / 100.0 * cfg["bateria_cap_kwh"]
        assert info["carga_rede_ac"] == pytest.approx(energia_dc / cfg["eficiencia_carga"])
        assert info["bat_carga"] == pytest.approx(energia_dc)
        assert ambiente.soc == pytest.approx(cfg["soc_max_pct"])
        assert info["bloqueio_carga_rede"] is None
    else:
        assert info["carga_rede_ac"] == info["bat_carga"] == 0.0
        assert ambiente.soc == pytest.approx(cfg["soc_inicial_pct"])
        assert info["bloqueio_carga_rede"] == "tarifa_alta"


@pytest.mark.parametrize("tarifa, bloqueio", [
    (0.70, "throughput_esgotado"), (1.10, "tarifa_alta"),
])
def test_env_carga_rede_prioriza_excedente(dia_fake, tarifa, bloqueio):
    cfg = dict(CONFIG, bat_throughput_max_kwh=1.0)
    ambiente = FazendaEnergyEnv(
        dia_fake.assign(solar_kw=50.0, eolico_kw=0.0), np.full(24, tarifa), cfg,
    )

    _, _, _, info = ambiente.step(ACAO_CARREGAR_REDE, 0, 2)

    assert info["carga_solar_ac"] == pytest.approx(1.0 / cfg["eficiencia_carga"])
    assert info["carga_rede_ac"] == 0.0
    assert info["bat_carga"] == pytest.approx(1.0)
    assert ambiente.bat_throughput_dia == pytest.approx(1.0)
    assert info["bloqueio_carga_rede"] == bloqueio


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
        "bonus_descarga_pico", "bonus_carga_pico_geracao",
        "pen_descarga_fora_pico",
        # Formulação econômica (transferida do SA)
        "pen_soc_final", "soc_alvo_final_pct", "w_ciclos", "w_pico_demanda",
    ]
    for chave in chaves:
        assert chave in CONFIG, f"Chave ausente em CONFIG: {chave}"


def test_tetos_kw_valores():
    assert TETOS_KW[0] < TETOS_KW[1] < TETOS_KW[2]
