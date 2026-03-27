"""Loop de treinamento IQL (Independent Q-Learning) cooperativo."""

import numpy as np
import pandas as pd

from .config import CONFIG
from .environment import FazendaEnergyEnv


def treinar(
    dias: list[pd.DataFrame],
    tarifa_24h: np.ndarray,
    agentes: dict,
    cfg: dict = CONFIG,
) -> tuple[list[float], list[float]]:
    """Treina os três agentes por `cfg['n_episodios']` episódios.

    Cada episódio simula um dia completo (24 timesteps). Os agentes
    aprendem de forma independente mas compartilham o mesmo reward
    cooperativo do ambiente.

    Args:
        dias       : lista de DataFrames diários (saída de carregar_dados)
        tarifa_24h : array (24,) com tarifa em R$/kWh
        agentes    : dict com chaves 'armazenamento', 'consumo', 'gerente'
        cfg        : dicionário de hiperparâmetros (padrão: CONFIG)

    Returns:
        (rewards_hist, custos_hist) — listas com valor acumulado por episódio
    """
    rewards_hist = []
    custos_hist  = []
    n_ep         = cfg["n_episodios"]

    for ep in range(n_ep):
        dados_dia = dias[np.random.randint(len(dias))]
        env       = FazendaEnergyEnv(dados_dia, tarifa_24h, cfg)
        est       = env.reset()
        s_disc    = env.discretizar(est)

        ep_reward = 0.0
        ep_custo  = 0.0

        for _ in range(24):
            a_arm  = agentes["armazenamento"].agir(s_disc)
            a_cons = agentes["consumo"].agir(s_disc)
            a_ger  = agentes["gerente"].agir(s_disc)

            prox_est, reward, done, info = env.step(a_arm, a_cons, a_ger)
            s2_disc = env.discretizar(prox_est)

            # Atualização cooperativa: mesmo reward para todos
            agentes["armazenamento"].aprender(s_disc, a_arm,  reward, s2_disc, done)
            agentes["consumo"].aprender(      s_disc, a_cons, reward, s2_disc, done)
            agentes["gerente"].aprender(      s_disc, a_ger,  reward, s2_disc, done)

            s_disc    = s2_disc
            ep_reward += reward
            ep_custo  += info["custo"]

        for ag in agentes.values():
            ag.decair_epsilon()

        rewards_hist.append(ep_reward)
        custos_hist.append(ep_custo)

        if (ep + 1) % 200 == 0:
            w     = min(100, ep + 1)
            r_med = np.mean(rewards_hist[-w:])
            c_med = np.mean(custos_hist[-w:])
            eps   = agentes["armazenamento"].epsilon
            n_est = agentes["armazenamento"].n_estados
            print(
                f"Ep {ep+1:>5}/{n_ep}  reward={r_med:>8.2f}  "
                f"custo=R${c_med:>5.2f}  \u03b5={eps:.3f}  estados={n_est}"
            )

    return rewards_hist, custos_hist
