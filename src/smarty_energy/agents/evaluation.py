"""Laco de avaliacao compartilhado pelas politicas, sem atualizar Q-tables."""

import numpy as np

from ..config import CONFIG


def avaliar_politica(escolher, dias, tarifa_24h, *, cfg: dict = CONFIG,
                     env_cls=None, n_dias: int = 30, tracker=None,
                     tracker_key: str = "politica",
                     propagar_soc: bool = True,
                     soc_inicial: float | None = None,
                     reiniciar_soc_em: frozenset[int] = frozenset()) -> dict:
    """Roda uma política por `n_dias` e devolve as métricas médias diárias.

    Fonte única do laço de avaliação — IQL, heurístico e sem-agente usam este
    mesmo caminho, garantindo que as métricas sejam comparáveis (mesmo env,
    mesmos dias, mesma propagação de SOC).

    Args:
        escolher     : callable ``(env, est) -> (a_arm, a_cons, a_ger)``.
        env_cls      : classe do ambiente; None usa `FazendaEnergyEnv`
                       (import tardio para evitar ciclo com environment.py).
        propagar_soc : se True, o SOC final de um dia inicia o dia seguinte.
        soc_inicial  : SOC do 1º dia; None usa `cfg['soc_inicial_pct']` (50%).
                       Permite continuar do SOC final do treino.
        reiniciar_soc_em : indices de dias que iniciam blocos independentes;
                   nesses indices o SOC volta ao valor inicial, inclusive no wrap.
        tracker      : `mcp.tracker.MetricsTracker` opcional, alimentado passo
                       a passo e por episódio.
    """
    if env_cls is None:
        from ..environment import FazendaEnergyEnv
        env_cls = FazendaEnergyEnv

    custos, redes, viols_soc, rewards = [], [], [], []
    soc_primeiro = cfg["soc_inicial_pct"] if soc_inicial is None else float(soc_inicial)
    soc_proximo  = soc_primeiro
    soc_final    = soc_primeiro

    for ep in range(n_dias):
        if ep % len(dias) in reiniciar_soc_em:
            soc_proximo = soc_primeiro
        env = env_cls(dias[ep % len(dias)], tarifa_24h, cfg)
        est = env.reset(soc_inicial=soc_proximo)

        custo_dia = rede_dia = reward_dia = 0.0
        viols = 0
        for _ in range(24):
            a_arm, a_cons, a_ger = escolher(env, est)
            est, reward, done, info = env.step(a_arm, a_cons, a_ger)
            custo_dia  += info["custo_r"]
            rede_dia   += info["rede_kwh"]
            reward_dia += info["reward"]
            if info["soc"] < cfg["soc_min_pct"]:
                viols += 1
            if tracker:
                tracker.registrar_passo(info, agente=tracker_key)
            if done:
                break

        if propagar_soc:
            soc_proximo = env.soc
        soc_final = env.soc

        custos.append(custo_dia)
        redes.append(rede_dia)
        viols_soc.append(viols)
        rewards.append(reward_dia)

        if tracker:
            tracker.fechar_episodio(
                agente=tracker_key, reward_total=reward_dia,
                custo_total=custo_dia, epsilon=0.0, cenario="REAL",
            )

    return {
        "n_dias": n_dias,
        "soc_inicial_pct": float(soc_primeiro),
        "soc_final_pct": float(soc_final),
        "custo_medio_dia_rs": float(np.mean(custos)),
        "custo_std": float(np.std(custos)),
        "rede_media_dia_kwh": float(np.mean(redes)),
        "violacoes_soc_media_h_dia": float(np.mean(viols_soc)),
        "reward_medio_dia": float(np.mean(rewards)),
    }
