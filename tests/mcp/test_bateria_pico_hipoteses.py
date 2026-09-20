"""Testes determinísticos para hipóteses sobre despacho da bateria no pico."""

import pandas as pd
import pytest

from smarty_energy.agents import IQLSystem, avaliar_politica
from smarty_energy.environment import FazendaEnergyEnv


def _dia(geracao_kw: float) -> pd.DataFrame:
    """Dia controlado cujo primeiro passo basta para testar a bateria."""
    return pd.DataFrame({
        "hora": range(24),
        "solar_kw": [geracao_kw] * 24,
        "eolico_kw": [0.0] * 24,
        "pivo_kw": [0.0] * 24,
        "captacao_kw": [0.0] * 24,
        "sede_kw": [1.0] * 24,
        "secador_kw": [1.0] * 24,
        "silo_kw": [0.5] * 24,
        "data": pd.Timestamp("2025-01-01"),
    })


_PESOS_SHAPING = (
    "w_custo", "w_estresse", "w_bonus_carga", "pen_soc", "pen_teto",
    "pen_producao", "pen_pcc", "pen_secador_meta", "pen_pivo_pico",
    "pen_secador_pico", "bonus_excedente", "bonus_soc_ok",
    "bonus_pivo_solar", "bonus_sec_excedente", "bonus_descarga_pico",
    "bonus_carga_pico_geracao", "pen_descarga_fora_pico",
    "pen_reserva_pre_pico", "pen_soc_final", "w_ciclos", "w_pico_demanda",
)


def _cfg_isolado(cfg, **ativos) -> dict:
    """CONFIG com todos os pesos de shaping zerados, exceto os passados."""
    novo = dict(cfg, reward_offset=0.0)
    for chave in _PESOS_SHAPING:
        novo[chave] = 0.0
    novo.update(ativos)
    return novo


def test_descarga_solicitada_sem_deficit_nao_entrega_energia(tarifa_fake, cfg):
    """`a_arm=2` nao descarrega quando a geracao ja atende a carga."""
    env = FazendaEnergyEnv(_dia(20.0), tarifa_fake, cfg)
    env.reset(soc_inicial=50.0)

    _, _, _, info = env.step(a_arm=2, a_cons=0, a_ger=2)

    assert info["a_arm"] == 2
    assert info["consumo_kw"] < info["geracao_kw"]
    assert info["bat_descarga"] == pytest.approx(0.0)


def test_descarga_solicitada_respeita_soc_minimo_e_throughput(tarifa_fake, cfg):
    """Mesmo com deficit, SoC minimo e throughput podem bloquear descarga."""
    cfg_soc_min = dict(cfg, bat_throughput_max_kwh=30.0)
    env_soc_min = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_soc_min)
    env_soc_min.reset(soc_inicial=cfg_soc_min["soc_min_pct"])
    _, _, _, info_soc_min = env_soc_min.step(a_arm=2, a_cons=0, a_ger=2)

    cfg_sem_throughput = dict(cfg, bat_throughput_max_kwh=0.0)
    env_sem_throughput = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_sem_throughput)
    env_sem_throughput.reset(soc_inicial=50.0)
    _, _, _, info_sem_throughput = env_sem_throughput.step(a_arm=2, a_cons=0, a_ger=2)

    assert info_soc_min["consumo_kw"] > info_soc_min["geracao_kw"]
    assert info_soc_min["bat_descarga"] == pytest.approx(0.0)
    assert info_soc_min["motivo_descarga_bloqueada"] == "soc_minimo"
    assert info_sem_throughput["consumo_kw"] > info_sem_throughput["geracao_kw"]
    assert info_sem_throughput["bat_descarga"] == pytest.approx(0.0)
    assert info_sem_throughput["motivo_descarga_bloqueada"] == "throughput_esgotado"


def test_descarga_bloqueada_sem_deficit_e_descarga_efetiva(tarifa_fake, cfg):
    env_sem_deficit = FazendaEnergyEnv(_dia(20.0), tarifa_fake, cfg)
    env_sem_deficit.reset(soc_inicial=50.0)
    _, _, _, info_sem_deficit = env_sem_deficit.step(a_arm=2, a_cons=0, a_ger=2)

    env_com_deficit = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg)
    env_com_deficit.reset(soc_inicial=50.0)
    _, _, _, info_com_deficit = env_com_deficit.step(a_arm=2, a_cons=0, a_ger=2)

    assert info_sem_deficit["motivo_descarga_bloqueada"] == "sem_deficit"
    assert info_com_deficit["bat_descarga"] > 0.0
    assert info_com_deficit["motivo_descarga_bloqueada"] is None


def test_niveis_de_descarga_limitam_a_fracao_do_deficit(tarifa_fake, cfg):
    descargas = []
    for acao in (2, 3, 4):
        env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg)
        env.reset(soc_inicial=95.0)
        _, _, _, info = env.step(a_arm=acao, a_cons=0, a_ger=2)
        descargas.append(info["bat_descarga"])

    assert descargas[0] == pytest.approx(descargas[2] * 0.25)
    assert descargas[1] == pytest.approx(descargas[2] * 0.50)
    assert descargas[2] > 0.0


def test_bonus_descarga_pico_recompensa_energia_util_entregue(tarifa_fake, cfg):
    cfg_bonus = _cfg_isolado(cfg, bonus_descarga_pico=2.0)
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_bonus)
    env.reset(soc_inicial=95.0)
    env.hora = 18

    _, reward, _, info = env.step(a_arm=4, a_cons=0, a_ger=2)

    esperado = info["bat_descarga"] * cfg_bonus["eficiencia_descarga"] * 2.0
    assert reward == pytest.approx(esperado)


def test_bonus_carga_pico_geracao_recompensa_kwh_armazenado_com_sol_forte(
    tarifa_fake, cfg
):
    cfg_carga = _cfg_isolado(cfg, bonus_carga_pico_geracao=2.0)

    # Sol forte (20 kW >= 15): bônus proporcional ao kWh armazenado
    env = FazendaEnergyEnv(_dia(20.0), tarifa_fake, cfg_carga)
    env.reset(soc_inicial=30.0)
    _, reward, _, info = env.step(a_arm=0, a_cons=0, a_ger=2)
    esperado = info["carga_solar_ac"] * cfg_carga["eficiencia_carga"] * 2.0
    assert info["bat_carga"] > 0.0
    assert reward == pytest.approx(esperado)

    # Sol fraco (14 kW < 15, mas ainda com excedente): bônus não dispara
    env_fraco = FazendaEnergyEnv(_dia(14.0), tarifa_fake, cfg_carga)
    env_fraco.reset(soc_inicial=30.0)
    _, reward_fraco, _, info_fraco = env_fraco.step(a_arm=0, a_cons=0, a_ger=2)
    assert info_fraco["bat_carga"] > 0.0
    assert reward_fraco == pytest.approx(0.0)


def test_pen_descarga_fora_pico_penaliza_kwh_util_fora_do_pico(tarifa_fake, cfg):
    cfg_pen = _cfg_isolado(cfg, pen_descarga_fora_pico=2.0)

    # Fora do pico (hora 12): penalidade proporcional ao kWh AC entregue
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_pen)
    env.reset(soc_inicial=95.0)
    env.hora = 12
    _, reward, _, info = env.step(a_arm=4, a_cons=0, a_ger=2)
    esperado = -info["bat_descarga"] * cfg_pen["eficiencia_descarga"] * 2.0
    assert not info["em_pico_tarifa"]
    assert info["bat_descarga"] > 0.0
    assert reward == pytest.approx(esperado)

    # No pico (hora 18): mesma descarga não é penalizada
    env_pico = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_pen)
    env_pico.reset(soc_inicial=95.0)
    env_pico.hora = 18
    _, reward_pico, _, info_pico = env_pico.step(a_arm=4, a_cons=0, a_ger=2)
    assert info_pico["em_pico_tarifa"]
    assert info_pico["bat_descarga"] > 0.0
    assert reward_pico == pytest.approx(0.0)


def test_reserva_pre_pico_penaliza_descarga_abaixo_do_alvo(tarifa_fake, cfg):
    cfg_reserva = _cfg_isolado(
        cfg,
        soc_reserva_pre_pico_pct=60.0,
        pen_reserva_pre_pico=2.0,
    )
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_reserva)
    env.reset(soc_inicial=50.0)
    env.hora = 12

    _, reward, _, info = env.step(a_arm=4, a_cons=0, a_ger=2)

    esperado = -cfg_reserva["pen_reserva_pre_pico"] * max(
        0.0, cfg_reserva["soc_reserva_pre_pico_pct"] - info["soc"]
    ) / 100.0 * info["bat_descarga"]
    assert not info["em_pico_tarifa"]
    assert info["pen_reserva_pre_pico"] == pytest.approx(esperado * -1)
    assert reward == pytest.approx(esperado)


def test_pen_ciclos_cobra_cada_kwh_movimentado(tarifa_fake, cfg):
    cfg_c = _cfg_isolado(cfg, w_ciclos=2.0)

    # Descarga: paga sobre o kWh retirado da bateria
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_c)
    env.reset(soc_inicial=95.0)
    env.hora = 12
    _, reward, _, info = env.step(a_arm=4, a_cons=0, a_ger=2)
    assert info["bat_descarga"] > 0.0
    assert reward == pytest.approx(-info["bat_descarga"] * 2.0)

    # Carga: paga sobre o kWh armazenado
    env_car = FazendaEnergyEnv(_dia(20.0), tarifa_fake, cfg_c)
    env_car.reset(soc_inicial=30.0)
    _, reward_car, _, info_car = env_car.step(a_arm=0, a_cons=0, a_ger=2)
    assert info_car["bat_carga"] > 0.0
    assert reward_car == pytest.approx(-info_car["bat_carga"] * 2.0)


def test_pen_pico_demanda_soma_do_dia_equivale_ao_pico_maximo(tarifa_fake, cfg):
    cfg_p = _cfg_isolado(cfg, w_pico_demanda=2.0)
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_p)
    env.reset(soc_inicial=50.0)
    soma, done = 0.0, False
    while not done:
        _, r, done, info = env.step(a_arm=1, a_cons=0, a_ger=2)
        soma += r
    pico = max(h["importacao"] for h in env.historico)
    assert pico > 0.0
    assert info["pico_importacao_dia"] == pytest.approx(pico)
    assert soma == pytest.approx(-2.0 * pico)


def test_pen_soc_final_cobra_deficit_terminal_da_bateria(tarifa_fake, cfg):
    cfg_f = _cfg_isolado(cfg, pen_soc_final=2.0, soc_alvo_final_pct=50.0)

    # Dia inteiro descarregando: termina abaixo do alvo → paga no último passo
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_f)
    env.reset(soc_inicial=50.0)
    done = False
    while not done:
        _, r, done, info = env.step(a_arm=4, a_cons=0, a_ger=2)
    assert info["soc"] < 50.0
    assert info["pen_soc_final"] == pytest.approx(2.0 * (50.0 - info["soc"]))
    assert r == pytest.approx(-2.0 * (50.0 - info["soc"]))

    # Dia carregando com sol: termina no alvo ou acima → não paga nada
    env_ok = FazendaEnergyEnv(_dia(20.0), tarifa_fake, cfg_f)
    env_ok.reset(soc_inicial=50.0)
    done = False
    while not done:
        _, r_ok, done, info_ok = env_ok.step(a_arm=0, a_cons=0, a_ger=2)
    assert info_ok["soc"] >= 50.0
    assert info_ok["pen_soc_final"] == 0.0
    assert r_ok == pytest.approx(0.0)


def test_carga_nao_importa_energia_da_rede_para_armazenar(tarifa_fake, cfg):
    """A acao de carga usa apenas excedente; ela nao implementa arbitragem da rede."""
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg)
    env.reset(soc_inicial=50.0)

    _, _, _, info = env.step(a_arm=0, a_cons=0, a_ger=2)

    assert info["consumo_kw"] > info["geracao_kw"]
    assert info["bat_carga"] == pytest.approx(0.0)
    assert info["importacao"] == pytest.approx(info["consumo_kw"])
    assert info["comando_bateria"] == "carregar_excedente"
    assert info["fluxo_bateria"] == "sem_movimento"


def test_carga_pela_rede_em_tarifa_baixa_contabiliza_custo(tarifa_fake, cfg):
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg)
    env.reset(soc_inicial=50.0)

    _, _, _, info = env.step(a_arm=5, a_cons=0, a_ger=2)

    assert info["comando_bateria"] == "carregar_rede"
    assert 0.0 < info["carga_rede_ac"] <= cfg["potencia_max_carga_rede_kw"]
    assert info["importacao"] == pytest.approx(
        info["consumo_kw"] + info["carga_rede_ac"]
    )
    assert info["custo_r"] == pytest.approx(
        info["importacao"] * tarifa_fake[0]
    )
    assert info["bloqueio_carga_rede"] is None


def test_carga_pela_rede_e_bloqueada_no_pico(tarifa_fake, cfg):
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg)
    env.reset(soc_inicial=50.0)
    env.hora = 18

    _, _, _, info = env.step(a_arm=5, a_cons=0, a_ger=2)

    assert info["carga_rede_ac"] == pytest.approx(0.0)
    assert info["bloqueio_carga_rede"] == "tarifa_alta"


def test_estado_tabular_nao_distingue_horas_dentro_do_mesmo_bloco(tarifa_fake, cfg):
    """O IQL distingue fases do pico sem aumentar a tupla de estado."""
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg)
    est = env.reset(soc_inicial=50.0)
    estados = {
        hora: env.discretizar({**est, "hora": hora, "tarifa": 1.10, "stress": 70.0})[0]
        for hora in (0, 6, 12, 16, 18, 19, 20, 21)
    }

    assert estados == {0: 0, 6: 1, 12: 2, 16: 3, 18: 4, 19: 4, 20: 5, 21: 6}


def test_avaliacao_com_propagacao_inicia_dia_seguinte_no_soc_anterior(tarifa_fake, cfg):
    """A avaliação encadeia o SoC final de um dia no reset do dia seguinte."""
    class EnvObservado(FazendaEnergyEnv):
        socs_de_reset: list[float | None] = []

        def reset(self, soc_inicial: float | None = None):
            type(self).socs_de_reset.append(soc_inicial)
            return super().reset(soc_inicial)

    EnvObservado.socs_de_reset = []
    resultado = avaliar_politica(
        lambda _env, _est: (2, 0, 2),
        [_dia(0.0), _dia(0.0)],
        tarifa_fake,
        cfg=cfg,
        env_cls=EnvObservado,
        n_dias=2,
        propagar_soc=True,
        soc_inicial=50.0,
    )

    assert EnvObservado.socs_de_reset[-1] == pytest.approx(cfg["soc_min_pct"])
    assert resultado["soc_final_pct"] == pytest.approx(cfg["soc_min_pct"])


def test_iql_atualiza_os_tres_agentes_com_o_mesmo_reward(cfg):
    """A recompensa cooperativa e compartilhada; o credito nao e individual."""
    iql = IQLSystem(dict(cfg, alpha=0.5, beta=0.01, epsilon_inicial=0.0))
    estado = (0, 5, 0, 0, 0, 0)
    proximo_estado = (0, 5, 0, 0, 0, 1)
    acoes = (2, 4, 1)

    iql.aprender_todos(estado, acoes, r=10.0, s2=proximo_estado, done=True)

    for nome, acao in zip(("armazenamento", "consumo", "gerente"), acoes):
        assert iql.agentes[nome].q_table[estado][acao] == pytest.approx(5.0)