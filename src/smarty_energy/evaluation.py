"""Funções de avaliação: executa heurístico e RL em dias reais."""

import numpy as np
import pandas as pd

from .config import CONFIG
from .environment import FazendaEnergyEnv
from .agents import AgentesHeuristicos

_heuristica = AgentesHeuristicos()


def rodar_heuristico(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray) -> list[dict]:
    """Executa os agentes heurísticos em um dia completo.

    Returns:
        historico — lista de 24 dicts com métricas horárias
    """
    env = FazendaEnergyEnv(dados_dia, tarifa_24h, CONFIG)
    est = env.reset()
    for _ in range(24):
        stress = _heuristica.stress_financeiro(est)
        a_arm  = _heuristica.armazenamento(est)
        a_cons = _heuristica.consumo(est, stress)
        a_ger  = _heuristica.gerente(est, stress)
        est, _, done, _ = env.step(a_arm, a_cons, a_ger)
        if done:
            break
    return env.historico


def rodar_rl(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray, agentes: dict) -> list[dict]:
    """Executa os agentes RL treinados em modo greedy (sem exploração).

    Returns:
        historico — lista de 24 dicts com métricas horárias
    """
    env    = FazendaEnergyEnv(dados_dia, tarifa_24h, CONFIG)
    est    = env.reset()
    s_disc = env.discretizar(est)
    for _ in range(24):
        a_arm  = agentes["armazenamento"].agir(s_disc, explorando=False)
        a_cons = agentes["consumo"].agir(s_disc, explorando=False)
        a_ger  = agentes["gerente"].agir(s_disc, explorando=False)
        prox, _, done, _ = env.step(a_arm, a_cons, a_ger)
        s_disc = env.discretizar(prox)
        if done:
            break
    return env.historico


def resumo_mes(historicos: list[list[dict]]) -> tuple[float, float, float, float]:
    """Calcula métricas médias diárias para um mês de simulações.

    Args:
        historicos : lista de históricos diários (cada um = 24 passos)

    Returns:
        (custo_medio, rede_media, violacoes_soc_media, reward_medio)
    """
    custo  = np.mean([sum(h["custo_r"]  for h in hist) for hist in historicos])
    rede   = np.mean([sum(h["rede_kwh"] for h in hist) for hist in historicos])
    viols  = np.mean([sum(1 for h in hist if h["soc"] < CONFIG["soc_min_pct"])
                      for hist in historicos])
    reward = np.mean([sum(h["reward"]   for h in hist) for hist in historicos])
    return custo, rede, viols, reward


def delta_pct(a: float, b: float) -> str:
    """Retorna variação percentual formatada de a para b."""
    return f"{((b - a) / abs(a) * 100):>+.1f} %" if a != 0 else "  n/a"


def identificar_cenarios(dias: list[pd.DataFrame]) -> dict[str, int]:
    """Identifica os índices dos três cenários de interesse.

    Returns:
        dict com chaves 'nublado', 'ensolarado', 'alto_consumo'
        mapeando para o índice em `dias`
    """
    ger_dia  = [d["solar_kw"].sum() + d["eolico_kw"].sum() for d in dias]
    cons_dia = [(d["pivo_kw"] + d["captacao_kw"] + d["sede_kw"] + d["silo_kw"]).sum()
                for d in dias]
    razao    = [cons_dia[i] / max(ger_dia[i], 0.1) for i in range(len(dias))]
    return {
        "nublado"     : int(np.argmin(ger_dia)),
        "ensolarado"  : int(np.argmax(ger_dia)),
        "alto_consumo": int(np.argmax(razao)),
    }
