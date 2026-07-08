"""Funções de avaliação: executa heurístico e RL em dias reais."""

import numpy as np
import pandas as pd

from .config import CONFIG
from .environment import FazendaEnergyEnv, ESPACO_ESTADOS_TOTAL
from .agents import AgentesHeuristicos

_heuristica = AgentesHeuristicos()


def cobertura_estados(agentes: dict, total: int = ESPACO_ESTADOS_TOTAL) -> dict:
    """Fração do espaço de estados discretos visitada no treino (bloco T2).

    Estados nunca visitados são a motivação da camada de julgamento: ali o RL
    não tem política aprendida. Reporta a fração sobre o total combinatório
    (``ESPACO_ESTADOS_TOTAL``), que é um teto — a cobertura real sobre estados
    *alcançáveis* é maior, pois parte das combinações é impossível.

    Args:
        agentes : dict de ``AgenteQL`` treinados (usa as chaves das Q-tables).

    Returns:
        dict com ``visitados`` (int), ``total`` (int) e ``fracao`` (0-1).
    """
    visitados: set = set()
    for ag in agentes.values():
        visitados |= set(ag.q_table.keys())
    n = len(visitados)
    return {"visitados": n, "total": total,
            "fracao": n / total if total else 0.0}


def rodar_sem_agente(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray) -> list[dict]:
    """Baseline SEM otimização — a fazenda 'como está hoje'.

    Comportamento fixo: bateria em modo 'manter' (sem gestão), nenhuma máquina
    cortada e teto de consumo liberal. Serve como referência de custo para
    comparar Heurístico e RL.
    """
    env = FazendaEnergyEnv(dados_dia, tarifa_24h, CONFIG)
    env.reset()
    for _ in range(24):
        _, _, done, _ = env.step(a_arm=1, a_cons=0, a_ger=2)
        if done:
            break
    return env.historico


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


def rodar_llm(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray, politica) -> list[dict]:
    """Executa uma PoliticaLLM em um dia completo (braço 'com MCP').

    Clone de ``rodar_rl`` trocando apenas o decisor: o LLM escolhe as 3 ações a
    cada hora. Ambiente, dias, reward e métricas são idênticos — é um A/B onde a
    única variável é o tomador de decisão. As métricas operacionais (latência,
    tokens, fallback) ficam acumuladas em ``politica.eventos``.

    Args:
        politica : instância de ``llm_policy.PoliticaLLM`` (com método ``agir``).

    Returns:
        historico — lista de 24 dicts com métricas horárias (idêntico a rodar_rl).
    """
    env = FazendaEnergyEnv(dados_dia, tarifa_24h, CONFIG)
    est = env.reset()
    for _ in range(24):
        a_arm, a_cons, a_ger = politica.agir(est)
        est, _, done, _ = env.step(a_arm, a_cons, a_ger)
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
