"""Funções de avaliação: executa heurístico e RL em dias reais."""

import numpy as np
import pandas as pd

from .config import CONFIG
from .environment import FazendaEnergyEnv, ESPACO_ESTADOS_TOTAL
from .agents import AgentesHeuristicos, SemAgente

_heuristica = AgentesHeuristicos()
_sem_agente = SemAgente()


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


def rodar_sem_agente(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray,
                     soc_inicial: float | None = None) -> list[dict]:
    """Baseline SEM otimização — a fazenda 'como está hoje'.

    Comportamento ingênuo: bateria inerte, teto liberal, secador no
    cronograma bruto da base e pivô tardio (16-23h, atravessa o pico — ver
    `SemAgente`). Serve como referência de custo para comparar Heurístico e RL.

    `soc_inicial` permite encadear dias (ver `rodar_sem_agente_mes`); None usa
    o SoC inicial padrão do CONFIG.
    """
    env = FazendaEnergyEnv(dados_dia, tarifa_24h, CONFIG)
    est = env.reset(soc_inicial=soc_inicial)
    agente = SemAgente()
    for _ in range(24):
        est, _, done, _ = env.step(*agente.agir(est))
        if done:
            break
    return env.historico


def rodar_heuristico(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray,
                     soc_inicial: float | None = None) -> list[dict]:
    """Executa os agentes heurísticos em um dia completo.

    Returns:
        historico — lista de 24 dicts com métricas horárias
    """
    env = FazendaEnergyEnv(dados_dia, tarifa_24h, CONFIG)
    est = env.reset(soc_inicial=soc_inicial)
    for _ in range(24):
        stress = _heuristica.stress_financeiro(est)
        a_arm  = _heuristica.armazenamento(est)
        a_cons = _heuristica.consumo(est, stress)
        a_ger  = _heuristica.gerente(est, stress)
        est, _, done, _ = env.step(a_arm, a_cons, a_ger)
        if done:
            break
    return env.historico


def rodar_rl(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray, agentes: dict,
             soc_inicial: float | None = None) -> list[dict]:
    """Executa os agentes RL treinados em modo greedy (sem exploração).

    Returns:
        historico — lista de 24 dicts com métricas horárias
    """
    env    = FazendaEnergyEnv(dados_dia, tarifa_24h, CONFIG)
    est    = env.reset(soc_inicial=soc_inicial)
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


# ──────────────────────────────────────────────────────────────
# Execução mensal com continuidade da bateria (SoC propagado)
# ──────────────────────────────────────────────────────────────

def _rodar_mes(dias, rodar_dia, propagar_soc: bool) -> list[list[dict]]:
    """Roda `rodar_dia(dia, soc_inicial)` em todos os dias, na ordem.

    Com `propagar_soc=True`, o SoC do fim de um dia inicia o próximo —
    a mesma continuidade real usada no treino (`training.treinar`). Devolve a
    lista de históricos por dia (mesmo formato de `[rodar_x(d, t) for d in dias]`),
    que as visualizações consomem.
    """
    resultados: list[list[dict]] = []
    soc = CONFIG["soc_inicial_pct"]
    for dia in dias:
        hist = rodar_dia(dia, soc if propagar_soc else None)
        resultados.append(hist)
        if propagar_soc and hist:
            soc = hist[-1]["soc"]     # SoC ao fim da hora 23 → início do dia seguinte
    return resultados


def rodar_sem_agente_mes(dias, tarifa_24h, *, propagar_soc: bool = True) -> list[list[dict]]:
    return _rodar_mes(dias, lambda d, s: rodar_sem_agente(d, tarifa_24h, s), propagar_soc)


def rodar_heuristico_mes(dias, tarifa_24h, *, propagar_soc: bool = True) -> list[list[dict]]:
    return _rodar_mes(dias, lambda d, s: rodar_heuristico(d, tarifa_24h, s), propagar_soc)


def rodar_rl_mes(dias, tarifa_24h, agentes, *, propagar_soc: bool = True) -> list[list[dict]]:
    return _rodar_mes(dias, lambda d, s: rodar_rl(d, tarifa_24h, agentes, s), propagar_soc)


def rodar_llm(dados_dia: pd.DataFrame, tarifa_24h: np.ndarray, politica,
              soc_inicial: float | None = None) -> list[dict]:
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
    est = env.reset(soc_inicial=soc_inicial)
    for _ in range(24):
        a_arm, a_cons, a_ger = politica.agir(est)
        est, _, done, _ = env.step(a_arm, a_cons, a_ger)
        if done:
            break
    return env.historico


def rodar_llm_mes(dias, tarifa_24h, politica, *, propagar_soc: bool = True) -> list[list[dict]]:
    return _rodar_mes(dias, lambda d, s: rodar_llm(d, tarifa_24h, politica, s), propagar_soc)


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


def classificar_dia(idx: int, dias: list[pd.DataFrame]) -> str:
    """Categoria de um dia usando quartis da geração e do consumo do mês.

    Enquanto `identificar_cenarios` devolve só os três dias extremos, esta
    função etiqueta qualquer dia — usada pelo servidor MCP para agrupar as
    métricas por cenário.

    Returns:
        'NUBLADO' | 'ENSOLARADO' | 'ALTO CONSUMO' | 'EQUILIBRADO'
    """
    ger_dia  = np.array([d["solar_kw"].sum() + d["eolico_kw"].sum() for d in dias])
    cons_dia = np.array([(d["pivo_kw"] + d["captacao_kw"] + d["sede_kw"] + d["silo_kw"]).sum()
                         for d in dias])
    g, c = ger_dia[idx], cons_dia[idx]
    q25_g, q75_g = np.quantile(ger_dia, [0.25, 0.75])
    q75_c        = np.quantile(cons_dia, 0.75)
    if g <= q25_g:
        return "NUBLADO"
    if c >= q75_c and g >= q75_g:
        return "ALTO CONSUMO"
    if g >= q75_g:
        return "ENSOLARADO"
    return "EQUILIBRADO"
