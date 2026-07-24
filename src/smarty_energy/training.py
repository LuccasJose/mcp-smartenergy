"""Loop de treinamento IQL (Independent Q-Learning) cooperativo."""

import copy
import time
from collections import defaultdict

import numpy as np
import pandas as pd

from .agents import avaliar_politica
from .config import CONFIG
from .environment import FazendaEnergyEnv


def metricas_convergencia(serie: list[float], janela: int | None = None,
                          tol: float = 0.05) -> dict:
    """Mede a estabilização de uma série de treino (bloco T2 — convergência).

    Compara a média das duas últimas janelas não-sobrepostas da série (custo ou
    reward por episódio). Se a variação relativa entre elas for menor que ``tol``,
    considera-se estabilizada — critério objetivo para a "curva que estabiliza"
    pedida no plano, no lugar de inspeção visual.

    Args:
        serie  : lista de valores por episódio (ex.: ``historico['custos']``).
        janela : tamanho de cada janela; padrão = 1/5 da série (mín. 1).
        tol    : limiar de variação relativa para declarar estabilidade.

    Returns:
        dict com ``media_final``, ``media_anterior``, ``variacao_relativa``,
        ``cv_final`` (coef. de variação da última janela) e ``estavel`` (bool).
        Retorna ``{'estavel': False, 'motivo': 'serie_curta'}`` se não houver
        duas janelas completas.
    """
    n = len(serie)
    if janela is None:
        janela = max(1, n // 5)
    if n < 2 * janela or janela == 0:
        return {"estavel": False, "motivo": "serie_curta", "n": n}

    ult = serie[-janela:]
    pen = serie[-2 * janela:-janela]
    media_ult = float(np.mean(ult))
    media_pen = float(np.mean(pen))
    var_rel = abs(media_ult - media_pen) / abs(media_pen) if media_pen else 0.0
    cv = float(np.std(ult) / abs(media_ult)) if media_ult else 0.0
    return {
        "media_final": media_ult,
        "media_anterior": media_pen,
        "variacao_relativa": var_rel,
        "cv_final": cv,
        "estavel": var_rel < tol,
        "janela": janela,
    }


def treinar(
    dias: list[pd.DataFrame],
    tarifa_24h: np.ndarray,
    agentes: dict,
    cfg: dict = CONFIG,
    *,
    env_cls=None,
    tracker=None,
    tracker_key: str = "iql_treino",
    log=None,
    eval_greedy_cada: int | None = None,
    dias_selecao: list[pd.DataFrame] | None = None,
) -> dict:
    """Treina os três agentes por `cfg['n_episodios']` episódios.

    Cada episódio simula um dia completo (24 timesteps). Os agentes
    aprendem de forma independente mas compartilham o mesmo reward
    cooperativo do ambiente.

    O SOC da bateria é propagado entre episódios consecutivos, simulando
    a continuidade real: o dia seguinte começa com a carga deixada pelo
    dia anterior. Os dias são percorridos em ordem (ep % len(dias)),
    reiniciando o ciclo após o último dia do mês.

    Seleção de modelo (o que sai do treino)
    ---------------------------------------
    A cada `eval_greedy_cada` episódios a política **greedy** é avaliada nos
    dias de seleção, e o melhor checkpoint é restaurado no fim. Isso substitui
    o critério antigo, que escolhia pela média móvel do custo *durante* o
    treino — número medido com ε-greedy ativo, que na prática não distingue
    política boa de ruim: medido em 3 sementes × 100k episódios, o custo de
    treino ficou cravado em ~R$74/dia enquanto a política greedy oscilava
    entre R$53 e R$89/dia. Trocar o critério vale ~18 % de custo.

    O treino também não melhora depois de ~10-15 mil episódios: os melhores
    checkpoints observados ficaram entre 2 mil e 13 mil, e daí em diante a
    curva só oscila. Horizontes muito longos gastam tempo sem retorno.

    Args:
        dias        : lista de DataFrames diários (saída de carregar_dados)
        tarifa_24h  : array (24,) com tarifa em R$/kWh
        agentes     : dict com chaves 'armazenamento', 'consumo', 'gerente'
        cfg         : dicionário de hiperparâmetros (padrão: CONFIG)
        env_cls     : classe do ambiente (None = FazendaEnergyEnv)
        tracker     : `mcp.tracker.MetricsTracker` opcional, alimentado passo a
                      passo e por episódio (usado pelo servidor MCP)
        tracker_key : rótulo do agente no tracker
        log         : callable de saída (None = print). O servidor MCP passa um
                      log em stderr para não poluir o canal do protocolo.
        eval_greedy_cada : intervalo (em episódios) da avaliação greedy que
                      seleciona o checkpoint. None = ~100 avaliações no treino;
                      0 desliga a seleção (fica com a política do último episódio).
        dias_selecao : dias usados na avaliação de seleção. None = todos.
                      Passe um subconjunto para não selecionar no mesmo conjunto
                      em que os resultados serão reportados.

    Returns:
        dict de histórico com as chaves: 'rewards', 'custos', 'epsilons'
        (listas por episódio), 'n_episodios', 'best_ep', 'best_custo_med'
        (custo greedy do checkpoint escolhido), 'curva_greedy' e
        'soc_final_pct'.
    """
    if env_cls is None:
        env_cls = FazendaEnergyEnv
    if log is None:
        log = print

    rewards_hist = []
    custos_hist  = []
    eps_hist     = []
    n_ep         = cfg["n_episodios"]
    soc_proximo  = cfg["soc_inicial_pct"]   # SOC inicial do 1º episódio

    # ── Seleção de modelo por avaliação greedy ─────────────────────
    # ~100 avaliações ao longo do treino, com piso de 100 episódios entre elas
    # (cada avaliação custa 31 dias × 24 passos — barato perto do treino).
    if eval_greedy_cada is None:
        eval_greedy_cada = max(100, n_ep // 100)
    dias_sel = dias_selecao if dias_selecao is not None else dias

    best_custo_greedy = float("inf")
    best_ep           = -1
    best_state        = None           # snapshot das q_tables
    curva_greedy      = []             # [(ep, custo_greedy)] — diagnóstico

    def _custo_greedy() -> float:
        """Custo médio diário da política greedy nos dias de seleção.

        Mesmo protocolo do número reportado pelo projeto (`evaluation.rodar_rl`):
        SOC reinicia em cada dia, sem propagação.
        """
        def escolher(env, est):
            s = env.discretizar(est)
            return (agentes["armazenamento"].agir(s, explorando=False),
                    agentes["consumo"].agir(s,       explorando=False),
                    agentes["gerente"].agir(s,       explorando=False))

        res = avaliar_politica(escolher, dias_sel, tarifa_24h, cfg=cfg,
                               env_cls=env_cls, n_dias=len(dias_sel),
                               propagar_soc=False)
        return res["custo_medio_dia_rs"]

    t0 = time.perf_counter()
    for ep in range(n_ep):
        dados_dia = dias[ep % len(dias)]            # sequencial, com wrap-around
        env       = env_cls(dados_dia, tarifa_24h, cfg)
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
            ep_custo  += info["custo_r"]
            if tracker:
                tracker.registrar_passo(info, agente=tracker_key)

        soc_proximo = env.soc                   # propaga SOC para o próximo dia

        for ag in agentes.values():
            ag.decair_epsilon()

        rewards_hist.append(ep_reward)
        custos_hist.append(ep_custo)
        eps_hist.append(agentes["armazenamento"].epsilon)

        if tracker:
            tracker.fechar_episodio(
                agente=tracker_key, reward_total=ep_reward, custo_total=ep_custo,
                epsilon=agentes["armazenamento"].epsilon, cenario="REAL",
            )

        # \u2500\u2500 Sele\u00e7\u00e3o: avalia a pol\u00edtica greedy e guarda a melhor \u2500\u2500\u2500\u2500\u2500\u2500\u2500
        if eval_greedy_cada and (ep + 1) % eval_greedy_cada == 0:
            c_greedy = _custo_greedy()
            curva_greedy.append((ep + 1, c_greedy))
            if c_greedy < best_custo_greedy:
                best_custo_greedy = c_greedy
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
            best_tag = (f"  [best ep {best_ep}: greedy R${best_custo_greedy:.2f}]"
                        if best_state else "")
            log(
                f"Ep {ep+1:>6}/{n_ep}  reward={r_med:>8.2f}  "
                f"custo=R${c_med:>5.2f}  \u03b5={eps:.3f}  estados={n_est}{best_tag}"
            )

    # \u2500\u2500 Restaura Q-tables do melhor checkpoint greedy \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    custo_greedy_final = _custo_greedy() if eval_greedy_cada else None
    if best_state is not None:
        log(f"\n  Sele\u00e7\u00e3o: restaurando Q-tables do ep {best_ep} "
            f"(greedy R${best_custo_greedy:.2f}/dia)")
        log(f"  Pol\u00edtica do \u00faltimo epis\u00f3dio: R${custo_greedy_final:.2f}/dia  "
            f"(ganho da sele\u00e7\u00e3o: R${custo_greedy_final - best_custo_greedy:+.2f})")
        for nome, snapshot in best_state.items():
            ag = agentes[nome]
            ag.q_table = defaultdict(lambda n=ag.n_acoes: np.zeros(n), snapshot)
    elif eval_greedy_cada:
        log("\n  [aviso] Sem snapshot \u2014 treino mais curto que o intervalo de avalia\u00e7\u00e3o")
    else:
        log("\n  [aviso] Sele\u00e7\u00e3o greedy desligada \u2014 fica a pol\u00edtica do \u00faltimo epis\u00f3dio")

    # M\u00e9tricas-resumo do treino (m\u00e9dias da janela final)
    janela = min(1000, len(custos_hist))
    custo_final  = float(np.mean(custos_hist[-janela:]))  if custos_hist  else None
    reward_final = float(np.mean(rewards_hist[-janela:])) if rewards_hist else None
    duracao_s = round(time.perf_counter() - t0, 1)

    # Hiperpar\u00e2metros-chave que distinguem um run (para o meta.json)
    hiperparametros = {
        k: cfg.get(k) for k in (
            "alpha", "gamma", "epsilon_inicial", "epsilon_final",
            "epsilon_decay", "bateria_cap_kwh",
        ) if k in cfg
    }

    # Snapshot COMPLETO do cfg efetivamente usado no treino \u2014 garante
    # reprodutibilidade (P2 do plano): pesos do reward, penalidades, efici\u00eancias,
    # limites etc. ficam registrados, n\u00e3o s\u00f3 os 6 hiperpar\u00e2metros de destaque.
    config_completo = dict(cfg)

    # Hist\u00f3rico de treino \u2014 a persist\u00eancia (versionada por run) fica a cargo
    # do chamador (ver smarty_energy.runs.salvar_run).
    return {
        "rewards" : rewards_hist,
        "custos"  : custos_hist,
        "epsilons": eps_hist,
        "n_episodios": n_ep,
        "best_ep" : best_ep,
        # Custo greedy (R$/dia) do checkpoint escolhido — mesma chave de antes,
        # agora com um número que reflete a política que de fato sai do treino.
        "best_custo_med": best_custo_greedy if best_state else None,
        "criterio_selecao": "greedy" if eval_greedy_cada else "nenhum",
        "curva_greedy": curva_greedy,
        "custo_greedy_ultimo_ep": custo_greedy_final,
        "n_dias_selecao": len(dias_sel),
        "soc_final_pct": float(soc_proximo),
        "custo_final": custo_final,
        "reward_final": reward_final,
        "duracao_s": duracao_s,
        "hiperparametros": hiperparametros,
        "config_completo": config_completo,
    }
