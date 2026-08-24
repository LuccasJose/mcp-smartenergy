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
    cfg_bonus = dict(cfg, bonus_descarga_pico=2.0, reward_offset=0.0)
    for chave in (
        "w_custo", "w_estresse", "w_bonus_carga", "pen_soc", "pen_teto",
        "pen_producao", "pen_pcc", "pen_secador_meta", "pen_pivo_pico",
        "pen_secador_pico", "bonus_excedente", "bonus_soc_ok",
        "bonus_pivo_solar", "bonus_sec_excedente",
    ):
        cfg_bonus[chave] = 0.0
    env = FazendaEnergyEnv(_dia(0.0), tarifa_fake, cfg_bonus)
    env.reset(soc_inicial=95.0)
    env.hora = 18

    _, reward, _, info = env.step(a_arm=4, a_cons=0, a_ger=2)

    esperado = info["bat_descarga"] * cfg_bonus["eficiencia_descarga"] * 2.0
    assert reward == pytest.approx(esperado)


def test_reserva_pre_pico_penaliza_descarga_abaixo_do_alvo(tarifa_fake, cfg):
    cfg_reserva = dict(
        cfg,
        soc_reserva_pre_pico_pct=60.0,
        pen_reserva_pre_pico=2.0,
        reward_offset=0.0,
    )
    for chave in (
        "w_custo", "w_estresse", "w_bonus_carga", "pen_soc", "pen_teto",
        "pen_producao", "pen_pcc", "pen_secador_meta", "pen_pivo_pico",
        "pen_secador_pico", "bonus_excedente", "bonus_soc_ok",
        "bonus_pivo_solar", "bonus_sec_excedente", "bonus_descarga_pico",
    ):
        cfg_reserva[chave] = 0.0
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