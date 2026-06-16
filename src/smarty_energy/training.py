"""Loop de treinamento IQL (Independent Q-Learning) cooperativo."""

import copy
import pickle
from collections import defaultdict

import numpy as np
import pandas as pd

from .config import CONFIG, OUTPUT_DIR
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

    O SOC da bateria é propagado entre episódios consecutivos, simulando
    a continuidade real: o dia seguinte começa com a carga deixada pelo
    dia anterior. Os dias são percorridos em ordem (ep % len(dias)),
    reiniciando o ciclo após o último dia do mês.

    Early stopping: a cada episódio, calcula a média móvel do custo
    sobre os últimos `EARLY_STOP_WINDOW` episódios; se o valor atual
    for o melhor já observado (após `min_ep_to_save` episódios), faz
    snapshot das Q-tables. Ao final, restaura as Q-tables do snapshot
    com menor custo médio — protege contra drift do IQL+Hysteretic.

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
    eps_hist     = []
    n_ep         = cfg["n_episodios"]
    soc_proximo  = cfg["soc_inicial_pct"]   # SOC inicial do 1º episódio

    # ── Early stopping: snapshot da melhor política observada ──────
    EARLY_STOP_WINDOW = 1000           # janela da média móvel
    min_ep_to_save    = max(EARLY_STOP_WINDOW, n_ep // 5)  # ignora primeiros 20%
    best_custo_med    = float("inf")
    best_ep           = -1
    best_state        = None           # snapshot das q_tables

    for ep in range(n_ep):
        dados_dia = dias[ep % len(dias)]            # sequencial, com wrap-around
        env       = FazendaEnergyEnv(dados_dia, tarifa_24h, cfg)
        est       = env.reset(soc_inicial=soc_proximo)
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

        soc_proximo = env.soc                   # propaga SOC para o próximo dia

        for ag in agentes.values():
            ag.decair_epsilon()

        rewards_hist.append(ep_reward)
        custos_hist.append(ep_custo)
        eps_hist.append(agentes["armazenamento"].epsilon)

        # \u2500\u2500 Early-stopping: snapshot quando a m\u00e9dia m\u00f3vel atinge novo m\u00ednimo \u2500\u2500
        if (ep + 1) >= EARLY_STOP_WINDOW:
            c_movel = float(np.mean(custos_hist[-EARLY_STOP_WINDOW:]))
            if (ep + 1) >= min_ep_to_save and c_movel < best_custo_med:
                best_custo_med = c_movel
                best_ep = ep + 1
                best_state = {
                    nome: copy.deepcopy(dict(ag.q_table))
                    for nome, ag in agentes.items()
                }

        # Print adaptativo: ~50 prints independente do tamanho do treino
        intervalo_print = max(200, n_ep // 50)
        if (ep + 1) % intervalo_print == 0:
            w     = min(intervalo_print, ep + 1)
            r_med = np.mean(rewards_hist[-w:])
            c_med = np.mean(custos_hist[-w:])
            eps   = agentes["armazenamento"].epsilon
            n_est = agentes["armazenamento"].n_estados
            best_tag = f"  [best ep {best_ep}: R${best_custo_med:.2f}]" if best_state else ""
            print(
                f"Ep {ep+1:>6}/{n_ep}  reward={r_med:>8.2f}  "
                f"custo=R${c_med:>5.2f}  \u03b5={eps:.3f}  estados={n_est}{best_tag}"
            )

    # \u2500\u2500 Restaura Q-tables do melhor checkpoint observado \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    if best_state is not None:
        custo_final = float(np.mean(custos_hist[-EARLY_STOP_WINDOW:]))
        print(
            f"\n  Early stopping: restaurando Q-tables do ep {best_ep} "
            f"(custo m\u00e9dio R${best_custo_med:.2f})"
        )
        print(f"  Custo m\u00e9dio nos \u00faltimos {EARLY_STOP_WINDOW} ep: R${custo_final:.2f}  "
              f"(ganho do checkpoint: R${custo_final - best_custo_med:+.2f})")
        for nome, snapshot in best_state.items():
            ag = agentes[nome]
            ag.q_table = defaultdict(lambda n=ag.n_acoes: np.zeros(n), snapshot)
    else:
        print(f"\n  [aviso] Sem snapshot \u2014 treino muito curto ou sem melhora detectada")

    # Persiste hist\u00f3rico de treino para revisualiza\u00e7\u00e3o sem retreinar
    models_dir = OUTPUT_DIR / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    hist_path = models_dir / "training_history.pkl"
    with open(hist_path, "wb") as f:
        pickle.dump({
            "rewards" : rewards_hist,
            "custos"  : custos_hist,
            "epsilons": eps_hist,
            "n_episodios": n_ep,
            "best_ep" : best_ep,
            "best_custo_med": best_custo_med,
        }, f)
    print(f"  Hist\u00f3rico de treino salvo em: {hist_path}")

    return rewards_hist, custos_hist
