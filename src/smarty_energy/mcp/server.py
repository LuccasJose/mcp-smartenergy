"""
MCP Server — SmartEnergy IQL (3 agentes Q-Learning cooperativos).

Expõe ferramentas para configurar, treinar, avaliar e diagnosticar o
sistema multi-agente que espelha o projeto Smart_Energy (FazendaEnergyEnv).

Dataset é baixado do Google Sheets na inicialização. SOC propaga entre
episódios (default), refletindo a continuidade real entre dias.
"""

import json
import os
import sys

from mcp.server.fastmcp import FastMCP

from ..config import (
    CONFIG, TETOS_KW, BOMBA_HORAS_ON, ID_FAZENDA, ajustar_decay,
    N_ACOES_ARMAZENAMENTO, N_ACOES_CONSUMO, N_ACOES_GERENTE,
)
from ..data_loader import carregar_dados, descrever_base
from ..environment import FazendaEnergyEnv, ESPACO_ESTADOS_TOTAL as N_ESTADOS_TOTAL
from ..evaluation import identificar_cenarios, classificar_dia
from ..agents import IQLSystem, AgentesHeuristicos, SemAgente
from .. import runs
from .tracker import MetricsTracker


def _log(msg: str) -> None:
    """Log do servidor — sempre em stderr, para não poluir o canal do protocolo."""
    print(msg, file=sys.stderr)


# ------------------------------------------------------------------ #
# Estado global do servidor                                            #
# ------------------------------------------------------------------ #

# Episódios por chamada de train_agents. Bem menor que o CONFIG do pipeline
# offline (100k), porque aqui o treino roda dentro de uma tool call; o
# decaimento de ε é reescalado para o horizonte pedido por `ajustar_decay`.
N_EPISODIOS_SERVIDOR = int(os.getenv("MCP_N_EPISODIOS", "1000"))

_log("Carregando dataset...")
DIAS, TARIFA_24H = carregar_dados()
DATASET_META = descrever_base(DIAS, TARIFA_24H)
_log(f"  {len(DIAS)} dias carregados (fazenda {DATASET_META['id_fazenda']}).")

iql = IQLSystem(ajustar_decay(CONFIG, N_EPISODIOS_SERVIDOR))
heuristico = AgentesHeuristicos(CONFIG)
sem_agente = SemAgente(CONFIG)
tracker = MetricsTracker()

# Env "atual" usado por get_current_state e step_environment (dia 0 por default).
_dia_atual_idx = 0
env = FazendaEnergyEnv(DIAS[_dia_atual_idx], TARIFA_24H, CONFIG)

# Host/porta do transporte HTTP — usados quando o servidor roda como
# processo central compartilhado por múltiplos clientes MCP (dashboard
# Streamlit + LLM-juiz). Configuráveis via env var para deploy remoto.
mcp = FastMCP(
    "mcpsmartenergy",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8000")),
)


# Pesos do reward — alteráveis em runtime via configure_reward_weights.
# Restrições físicas (pcc_max_kw, soc_min_pct, bat_throughput_max_kwh, etc.)
# ficam imutáveis para preservar fidelidade ao projeto Smart_Energy real.
_REWARD_WEIGHT_KEYS = (
    "w_custo", "w_estresse", "w_bonus_carga",
    "pen_soc", "pen_teto", "pen_producao", "pen_pcc",
    "pen_secador_meta", "pen_sede_desvio",
    "pen_pivo_pico", "pen_secador_pico",
    "bonus_excedente", "bonus_soc_ok",
    "bonus_pivo_solar", "bonus_sec_excedente",
)
_DEFAULT_REWARD_WEIGHTS = {k: CONFIG[k] for k in _REWARD_WEIGHT_KEYS}


def _err(e: Exception) -> str:
    return json.dumps({"erro": f"{type(e).__name__}: {e}"}, indent=2, default=str)


# ------------------------------------------------------------------ #
# Configuração                                                         #
# ------------------------------------------------------------------ #

@mcp.tool()
def configure_agents(
    n_episodios: int | None = None,
    alpha: float | None = None,
    gamma: float | None = None,
    beta: float | None = None,
    epsilon_inicial: float | None = None,
    epsilon_final: float | None = None,
    epsilon_decay: float | None = None,
) -> str:
    """Atualiza hiperparâmetros dos 3 agentes IQL (sem destruir Q-tables).

    Use `reset_environment(reset_agents=True)` para também zerar as Q-tables.
    Parâmetros omitidos mantêm o valor atual.
    """
    try:
        novos = {}
        if n_episodios is not None:
            if n_episodios < 1:
                return json.dumps({"erro": "n_episodios deve ser >= 1"}, indent=2)
            novos["n_episodios"] = n_episodios
        if alpha is not None:
            if not (0.0 < alpha <= 1.0):
                return json.dumps({"erro": "alpha em (0, 1]"}, indent=2)
            novos["alpha"] = alpha
        if beta is not None:
            if not (0.0 < beta <= 1.0):
                return json.dumps({"erro": "beta em (0, 1]"}, indent=2)
            novos["beta"] = beta
        if gamma is not None:
            if not (0.0 < gamma < 1.0):
                return json.dumps({"erro": "gamma em (0, 1)"}, indent=2)
            novos["gamma"] = gamma
        if epsilon_inicial is not None: novos["epsilon_inicial"] = epsilon_inicial
        if epsilon_final is not None:   novos["epsilon_final"]   = epsilon_final
        if epsilon_decay is not None:   novos["epsilon_decay"]   = epsilon_decay

        iql.reconfigurar(novos)
        return json.dumps({
            "status": "agentes reconfigurados",
            "hiperparametros_atuais": {n: iql.agentes[n].get_info()
                                        for n in iql.agentes},
            "n_episodios": iql.n_episodios,
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def configure_reward_weights(
    w_custo: float | None = None,
    w_estresse: float | None = None,
    w_bonus_carga: float | None = None,
    pen_soc: float | None = None,
    pen_teto: float | None = None,
    pen_producao: float | None = None,
    pen_pcc: float | None = None,
    pen_secador_meta: float | None = None,
    pen_sede_desvio: float | None = None,
    pen_pivo_pico: float | None = None,
    pen_secador_pico: float | None = None,
    bonus_excedente: float | None = None,
    bonus_soc_ok: float | None = None,
    bonus_pivo_solar: float | None = None,
    bonus_sec_excedente: float | None = None,
) -> str:
    """Ajusta os pesos do reward cooperativo em runtime.

    ATENÇÃO: Q-tables já treinadas ficam parcialmente obsoletas após
    mudar pesos. Sempre chame train_agents() antes de avaliar.

    Todos os pesos devem ser ≥ 0 — o sinal (penalidade vs bônus) está
    embutido na fórmula do reward em FazendaEnergyEnv. Parâmetros
    omitidos mantêm o valor atual. Restrições físicas (PCC, SOC min/max,
    capacidade de bateria, etc.) não são alteráveis para preservar
    fidelidade ao projeto Smart_Energy real.
    """
    try:
        candidatos = {
            "w_custo": w_custo, "w_estresse": w_estresse,
            "w_bonus_carga": w_bonus_carga,
            "pen_soc": pen_soc, "pen_teto": pen_teto,
            "pen_producao": pen_producao, "pen_pcc": pen_pcc,
            "pen_secador_meta": pen_secador_meta,
            "pen_sede_desvio": pen_sede_desvio,
            "pen_pivo_pico": pen_pivo_pico,
            "pen_secador_pico": pen_secador_pico,
            "bonus_excedente": bonus_excedente,
            "bonus_soc_ok": bonus_soc_ok,
            "bonus_pivo_solar": bonus_pivo_solar,
            "bonus_sec_excedente": bonus_sec_excedente,
        }
        novos = {k: float(v) for k, v in candidatos.items() if v is not None}

        if not novos:
            return json.dumps({
                "status": "nenhum peso fornecido",
                "pesos_atuais": {k: CONFIG[k] for k in _REWARD_WEIGHT_KEYS},
                "defaults": _DEFAULT_REWARD_WEIGHTS,
            }, indent=2)

        invalidos = [k for k, v in novos.items() if v < 0]
        if invalidos:
            return json.dumps({
                "erro": f"Pesos devem ser >= 0: {invalidos}",
                "nota": "O sinal (penalidade vs bônus) está na fórmula do reward.",
            }, indent=2)

        CONFIG.update(novos)
        # O IQL trabalha sobre uma cópia do CONFIG (com o decay ajustado ao
        # horizonte do servidor), então precisa receber os pesos novos também —
        # é o cfg que ele passa ao env em treino e avaliação.
        iql.cfg.update(novos)
        # Recria env global para refletir mudanças em step_environment.
        # Treino/avaliação criam env próprio por dia e já usam o CONFIG novo.
        global env
        env = FazendaEnergyEnv(DIAS[_dia_atual_idx], TARIFA_24H, CONFIG)

        delta_vs_default = {
            k: round(CONFIG[k] - _DEFAULT_REWARD_WEIGHTS[k], 4)
            for k in _REWARD_WEIGHT_KEYS
            if abs(CONFIG[k] - _DEFAULT_REWARD_WEIGHTS[k]) > 1e-9
        }

        return json.dumps({
            "status": "pesos atualizados",
            "alterados_nesta_chamada": novos,
            "pesos_atuais": {k: CONFIG[k] for k in _REWARD_WEIGHT_KEYS},
            "delta_vs_default": delta_vs_default,
            "aviso": ("Q-tables atuais foram aprendidas com pesos diferentes. "
                      "Chame train_agents() antes de avaliar a nova política."),
        }, indent=2)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Treino                                                                #
# ------------------------------------------------------------------ #

@mcp.tool()
def train_agents(n_episodios: int = 0) -> str:
    """Treina os 3 agentes IQL com reward cooperativo.

    Dias percorridos sequencialmente com wrap-around. SOC propaga entre
    episódios (continuidade real). Use n_episodios=0 para usar o configurado.
    """
    try:
        tracker.limpar("iql_treino")
        if n_episodios > 0:
            iql.n_episodios = n_episodios
        sumario = iql.treinar(DIAS, TARIFA_24H, FazendaEnergyEnv,
                              tracker=tracker, log=_log)
        return json.dumps(sumario, indent=2)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Avaliação                                                             #
# ------------------------------------------------------------------ #

@mcp.tool()
def evaluate_agents(n_dias: int = 30, propagar_soc: bool = True) -> str:
    """Avalia o IQL em modo greedy por n_dias percorrendo o dataset.

    propagar_soc=True (default) mantém o SOC final como inicial do próximo
    dia, refletindo continuidade real. False reseta para soc_inicial em
    cada dia (útil para diagnóstico isolado).
    """
    try:
        tracker.limpar("iql_eval")
        resultado = iql.avaliar(
            DIAS, TARIFA_24H, FazendaEnergyEnv,
            n_dias=n_dias, tracker=tracker, propagar_soc=propagar_soc,
        )
        return json.dumps(resultado, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def compare_strategies(n_dias: int = 30, propagar_soc: bool = True) -> str:
    """Compara IQL vs Heurístico vs SemAgente nos mesmos n_dias do dataset.

    Cada estratégia roda independentemente sobre as mesmas datas e a mesma
    sequência de SOC inicial. Popula tracker com chaves 'iql_eval_cmp',
    'heuristico', 'sem_agente'.
    """
    try:
        tracker.limpar("iql_eval")
        tracker.limpar("iql_eval_cmp")
        tracker.limpar("heuristico")
        tracker.limpar("sem_agente")

        r_iql  = iql.avaliar(DIAS, TARIFA_24H, FazendaEnergyEnv,
                              n_dias=n_dias, tracker=tracker,
                              propagar_soc=propagar_soc)
        # iql escreve em 'iql_eval'; renomeia para não conflitar
        tracker.passos["iql_eval_cmp"]     = tracker.passos.pop("iql_eval", [])
        tracker.episodios["iql_eval_cmp"]  = tracker.episodios.pop("iql_eval", [])

        r_heur = heuristico.avaliar(DIAS, TARIFA_24H, FazendaEnergyEnv,
                                     n_dias=n_dias, tracker=tracker,
                                     tracker_key="heuristico",
                                     propagar_soc=propagar_soc)
        r_sem  = sem_agente.avaliar(DIAS, TARIFA_24H, FazendaEnergyEnv,
                                     n_dias=n_dias, tracker=tracker,
                                     tracker_key="sem_agente",
                                     propagar_soc=propagar_soc)

        resultados = {
            "IQL":        r_iql,
            "Heuristico": r_heur,
            "SemAgente":  r_sem,
            "tracker_keys": ["iql_eval_cmp", "heuristico", "sem_agente"],
        }
        custo_iql, custo_heur, custo_sem = (r["custo_medio_dia_rs"]
                                             for r in (r_iql, r_heur, r_sem))
        if custo_sem > 0:
            resultados["reducao_iql_vs_sem_pct"]  = round(
                (custo_sem - custo_iql) / custo_sem * 100, 2)
            resultados["reducao_iql_vs_heur_pct"] = round(
                (custo_heur - custo_iql) / custo_heur * 100, 2) if custo_heur > 0 else None

        return json.dumps(resultados, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def run_episode(mode: str = "eval", dia_idx: int | None = None) -> str:
    """Executa 1 dia completo e retorna o trace hora-a-hora.

    mode: "eval" (greedy) ou "train" (ε-greedy com aprendizado online)
    dia_idx: índice do dia no dataset (None = dia atual selecionado)
    """
    try:
        idx = _dia_atual_idx if dia_idx is None else int(dia_idx)
        if not (0 <= idx < len(DIAS)):
            return json.dumps({"erro": f"dia_idx fora do range [0, {len(DIAS)-1}]"}, indent=2)

        tracker.limpar("iql_trace")
        e = FazendaEnergyEnv(DIAS[idx], TARIFA_24H, CONFIG)
        est = e.reset(soc_inicial=iql.soc_propagado)
        s = e.discretizar(est)

        explore = mode == "train"
        reward_total = 0.0
        custo_total  = 0.0

        for _ in range(24):
            acoes = iql.agir_todos(s, explorando=explore)
            prox, reward, done, info = e.step(*acoes)
            s2 = e.discretizar(prox)
            if explore:
                iql.aprender_todos(s, acoes, reward, s2, done)
            s = s2
            tracker.registrar_passo(info, agente="iql_trace")
            reward_total += reward
            custo_total  += info["custo_r"]

        return json.dumps({
            "mode": mode,
            "dia_idx": idx,
            "data": DATASET_META.get("data_inicio") if idx == 0 else str(DIAS[idx]["data"].iloc[0])[:10],
            "cenario": classificar_dia(idx, DIAS),
            "reward_total": round(reward_total, 4),
            "custo_total_rs": round(custo_total, 4),
            "soc_final_pct": round(e.soc, 2),
            "trace": tracker.get_trace_ultimo_episodio("iql_trace"),
        }, indent=2, default=str)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Métricas                                                              #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_training_metrics() -> str:
    """Métricas do último treino: rewards/custos/epsilons + info dos 3 agentes."""
    return json.dumps({
        "treino": tracker.get_training_metrics("iql_treino"),
        "agentes": {n: ag.get_info() for n, ag in iql.agentes.items()},
    }, indent=2)


@mcp.tool()
def get_qtables_info() -> str:
    """Estatísticas das Q-tables dos 3 agentes IQL."""
    return json.dumps({n: ag.get_info() for n, ag in iql.agentes.items()}, indent=2)


@mcp.tool()
def get_td_error_series(agente: str = "armazenamento") -> str:
    """Série completa de TD-error (janela rolante de até 5000 updates) de 1 agente.

    Usado pelo dashboard para plotar a curva de convergência por agente —
    `get_qtables_info` só traz o resumo (`td_error_recente`), não a série.

    agente: "armazenamento", "consumo" ou "gerente".
    """
    try:
        if agente not in iql.agentes:
            return json.dumps({
                "erro": f"agente inválido: {agente}. Use um de {list(iql.agentes)}",
            }, indent=2)
        ag = iql.agentes[agente]
        return json.dumps({
            "agente": agente,
            "n_pontos": len(ag.td_errors),
            "td_errors": [round(float(v), 6) for v in ag.td_errors],
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_learning_curve(janela_media_movel: int = 20) -> str:
    """Curva de aprendizado (reward e custo por episódio com média móvel)."""
    return json.dumps(tracker.get_learning_curve("iql_treino",
                                                  janela=janela_media_movel), indent=2)


@mcp.tool()
def get_eval_metrics(agente: str = "iql_eval") -> str:
    """Métricas da última avaliação.

    `agente`: "iql_eval" (default), "iql_eval_cmp", "heuristico", "sem_agente".
    """
    return json.dumps(tracker.get_eval_metrics(agente), indent=2)


@mcp.tool()
def get_peak_offpeak_stats(agente: str = "iql_eval") -> str:
    """Consumo por carga separado por período tarifário (pico vs fora-pico)."""
    return json.dumps(tracker.get_peak_offpeak_stats(agente), indent=2)


@mcp.tool()
def get_stats_por_cenario(agente: str = "iql_eval") -> str:
    """Reward/custo médio por cenário climático (NUBLADO/ENSOLARADO/ALTO CONSUMO/EQUILIBRADO).

    Como o env real não classifica cenário automaticamente, o tracker
    armazena 'REAL'; para uma análise por cenário use identify_scenarios
    com um trace específico.
    """
    return json.dumps(tracker.get_stats_por_cenario(agente), indent=2)


@mcp.tool()
def get_hourly_violations(agente: str = "iql_eval") -> str:
    """Violações (SOC, PCC, teto) agregadas por hora-do-dia.

    Útil para o LLM-juiz identificar em quais horas a política falha mais.
    """
    return json.dumps(tracker.get_hourly_violations(agente), indent=2)


# ------------------------------------------------------------------ #
# Cenários e dataset                                                    #
# ------------------------------------------------------------------ #

@mcp.tool()
def identify_scenarios() -> str:
    """Índices dos 3 dias extremos do dataset (nublado/ensolarado/alto_consumo)."""
    cen = identificar_cenarios(DIAS)
    enriquecido = {}
    for nome, idx in cen.items():
        dia = DIAS[idx]
        enriquecido[nome] = {
            "dia_idx": idx,
            "data": str(dia["data"].iloc[0])[:10],
            "geracao_total_kwh": round(float(dia["solar_kw"].sum() + dia["eolico_kw"].sum()), 2),
            "consumo_total_kwh": round(float((dia["pivo_kw"] + dia["captacao_kw"]
                                              + dia["sede_kw"] + dia["silo_kw"]).sum()), 2),
            "categoria": classificar_dia(idx, DIAS),
        }
    return json.dumps(enriquecido, indent=2)


@mcp.tool()
def get_dataset_info() -> str:
    """Informações sobre o dataset carregado (fazenda, n_dias, range de datas, tarifa)."""
    return json.dumps({
        **DATASET_META,
        "tarifa_horaria_rs_kwh": [round(float(t), 4) for t in TARIFA_24H],
        "horas_pico_tarifa": [int(h) for h in range(24) if TARIFA_24H[h] > 0.9],
    }, indent=2)


@mcp.tool()
def select_day(dia_idx: int) -> str:
    """Seleciona um dia específico do dataset para get_current_state / step_environment."""
    try:
        global _dia_atual_idx, env
        if not (0 <= dia_idx < len(DIAS)):
            return json.dumps({"erro": f"dia_idx fora de [0, {len(DIAS)-1}]"}, indent=2)
        _dia_atual_idx = dia_idx
        env = FazendaEnergyEnv(DIAS[dia_idx], TARIFA_24H, CONFIG)
        return json.dumps({
            "status": "dia selecionado",
            "dia_idx": dia_idx,
            "data": str(DIAS[dia_idx]["data"].iloc[0])[:10],
            "categoria": classificar_dia(dia_idx, DIAS),
        }, indent=2)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Ambiente                                                              #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_current_state() -> str:
    """Estado atual do env (dia selecionado, hora corrente)."""
    return json.dumps({
        "dia_idx": _dia_atual_idx,
        "data": str(DIAS[_dia_atual_idx]["data"].iloc[0])[:10],
        **{k: (round(float(v), 4) if isinstance(v, (int, float)) else v)
           for k, v in env.get_full_state().items()},
    }, indent=2)


@mcp.tool()
def reset_environment(reset_agents: bool = False, dia_idx: int | None = None) -> str:
    """Reinicia o env (e opcionalmente as Q-tables).

    Se dia_idx for fornecido, troca o dia selecionado. SOC inicial vem do
    soc_propagado mantido pelo IQLSystem.
    """
    try:
        global env, _dia_atual_idx
        if dia_idx is not None:
            if not (0 <= dia_idx < len(DIAS)):
                return json.dumps({"erro": f"dia_idx fora de [0, {len(DIAS)-1}]"}, indent=2)
            _dia_atual_idx = dia_idx
        env = FazendaEnergyEnv(DIAS[_dia_atual_idx], TARIFA_24H, CONFIG)
        env.reset(soc_inicial=iql.soc_propagado)

        if reset_agents:
            iql.reset_qtables()
            tracker.limpar()

        return json.dumps({
            "status": "ambiente reiniciado",
            "agentes_reiniciados": reset_agents,
            "dia_idx": _dia_atual_idx,
            "estado": {k: (round(float(v), 4) if isinstance(v, (int, float)) else v)
                       for k, v in env.get_full_state().items()},
        }, indent=2)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Integração com agente externo                                         #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_observation() -> str:
    """Observação atual + estado discretizado para um agente externo."""
    try:
        est = env._estado()
        s = env.discretizar(est)
        return json.dumps({
            "obs": {k: (bool(v) if isinstance(v, bool) else
                        round(float(v), 4) if isinstance(v, (int, float)) else v)
                    for k, v in est.items()},
            "state_discrete": list(s),
            "state_index": str(s),
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def step_environment(a_arm: int, a_cons: int, a_ger: int) -> str:
    """Avança 1 hora no env atual com as 3 ações fornecidas.

    a_arm: 0=carregar, 1=manter, 2=descarregar
    a_cons: bitmask 3 bits (bit0=corta pivô, bit1=corta bomba, bit2=corta secador)
    a_ger: 0=conservador(20kW), 1=moderado(30kW), 2=liberal(40kW)
    """
    try:
        if a_arm not in (0, 1, 2):
            return json.dumps({"erro": f"a_arm inválido: {a_arm}"}, indent=2)
        if not (0 <= a_cons <= 7):
            return json.dumps({"erro": f"a_cons inválido: {a_cons}"}, indent=2)
        if a_ger not in (0, 1, 2):
            return json.dumps({"erro": f"a_ger inválido: {a_ger}"}, indent=2)

        prox, reward, done, info = env.step(a_arm, a_cons, a_ger)
        s2 = env.discretizar(prox)
        return json.dumps({
            "reward": round(reward, 6),
            "done": done,
            "next_state_discrete": list(s2),
            "obs": {k: (bool(v) if isinstance(v, bool) else
                        round(float(v), 4) if isinstance(v, (int, float)) else v)
                    for k, v in prox.items()},
            "info": {k: (bool(v) if isinstance(v, bool) else
                         round(float(v), 6) if isinstance(v, (int, float)) else v)
                     for k, v in info.items()},
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_actions(explore: bool = False) -> str:
    """Ações escolhidas pelos 3 agentes IQL para o estado atual + Q-values."""
    try:
        est = env._estado()
        s = env.discretizar(est)
        out = {"state_discrete": list(s)}
        for nome, ag in iql.agentes.items():
            a = ag.agir(s, explorando=explore)
            q = ag.q_table[s]
            top = sorted(enumerate(q.tolist()), key=lambda x: -x[1])[:3]
            out[nome] = {
                "action": a,
                "q_value": round(float(q[a]), 6),
                "top_actions": [{"a": aid, "q": round(qv, 6)} for aid, qv in top],
                "epsilon": round(ag.epsilon, 4),
            }
        return json.dumps(out, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def save_qtables(dir_path: str = "", label: str = "") -> str:
    """Salva as 3 Q-tables do treino atual.

    Sem `dir_path`, grava um run versionado em `outputs/runs/<run_id>/` —
    o mesmo formato que o pipeline offline (`main.py`) e os dashboards leem,
    incluindo o CONFIG efetivo do treino no meta.json. Use `label` para
    rotular o run. Com `dir_path`, grava só os 3 pickles no diretório dado.
    """
    try:
        if dir_path:
            iql.save_all(dir_path)
            return json.dumps({
                "status": "Q-tables salvas",
                "dir": dir_path,
                "arquivos": [f"qtable_{n}.pkl" for n in iql.agentes],
            }, indent=2)

        if iql.ultimo_hist is None:
            return json.dumps({
                "erro": "nenhum treino nesta sessão — rode train_agents() antes, "
                        "ou informe dir_path para salvar só os pickles.",
            }, indent=2)

        run_id = runs.salvar_run(iql.agentes, iql.ultimo_hist,
                                 fonte_dados=f"MCP · {DATASET_META['id_fazenda']}")
        if label:
            runs.definir_label(run_id, label)
        return json.dumps({
            "status": "run salvo",
            "run_id": run_id,
            "caminho": str(runs.caminho_run(run_id)),
            "nota": "visível em main.py --replot e nos dashboards.",
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def load_qtables(dir_path: str = "", run_id: str = "") -> str:
    """Carrega Q-tables salvas.

    Sem argumentos, carrega o run mais recente de `outputs/runs/` (inclusive
    os treinados pelo pipeline offline). Informe `run_id` para escolher um
    run específico ou `dir_path` para ler 3 pickles soltos.
    """
    try:
        if dir_path:
            iql.load_all(dir_path)
            origem = dir_path
        else:
            rid = run_id or runs.run_mais_recente()
            if rid is None:
                return json.dumps({"erro": "nenhum run em outputs/runs/"}, indent=2)
            runs.carregar_run(rid, iql.agentes)
            origem = rid
        return json.dumps({
            "status": "Q-tables carregadas",
            "origem": origem,
            "agentes": {n: ag.get_info() for n, ag in iql.agentes.items()},
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_financeiro_state() -> str:
    """Estado atual do AgenteFinanceiro do env: saldo de créditos + estresse atual."""
    try:
        est = env._estado()
        return json.dumps({
            "saldo_creditos_kwh": round(float(env.fin.saldo_creditos), 4),
            "estresse_atual": round(float(est["stress"]), 2),
            "tarifa_atual_rs_kwh": round(float(est["tarifa"]), 4),
            "em_pico_tarifa": est["em_pico_tarifa"],
            "credito_inicial_kwh": CONFIG["credito_inicial_kwh"],
            "tarifa_estresse_limiar_rs_kwh": CONFIG["tarifa_estresse_limiar"],
        }, indent=2)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Diagnóstico consolidado e schema                                      #
# ------------------------------------------------------------------ #

@mcp.tool()
def health_report() -> str:
    """Payload consolidado para um LLM avaliar o sistema:
    - cobertura das 3 Q-tables / TD-error recente
    - sumário do último treino
    - sumário da última avaliação
    - comparação IQL vs baselines (se compare_strategies foi rodado)
    - alertas heurísticos
    """
    try:
        info_ags = {n: ag.get_info() for n, ag in iql.agentes.items()}
        cobertura = {n: round(info["n_estados_visitados"] / N_ESTADOS_TOTAL * 100, 2)
                     for n, info in info_ags.items()}

        treino = tracker.get_training_metrics("iql_treino")
        treino_resumo = {k: v for k, v in treino.items()
                         if k not in ("rewards_hist", "custos_hist", "epsilons")}

        eval_iql  = tracker.get_eval_metrics("iql_eval")
        eval_cmp  = tracker.get_eval_metrics("iql_eval_cmp")
        eval_heur = tracker.get_eval_metrics("heuristico")
        eval_sem  = tracker.get_eval_metrics("sem_agente")

        comparacao = None
        if all("custo_medio_dia_rs" in m for m in (eval_cmp, eval_heur, eval_sem)):
            c_iql, c_heur, c_sem = (m["custo_medio_dia_rs"] for m in (eval_cmp, eval_heur, eval_sem))
            comparacao = {
                "custo_iql_rs_dia":  round(c_iql, 4),
                "custo_heuristico_rs_dia": round(c_heur, 4),
                "custo_sem_agente_rs_dia": round(c_sem, 4),
                "reducao_iql_vs_sem_pct":  round((c_sem - c_iql) / c_sem * 100, 2) if c_sem > 0 else None,
                "reducao_iql_vs_heur_pct": round((c_heur - c_iql) / c_heur * 100, 2) if c_heur > 0 else None,
            }

        alertas = []
        cob_min = min(cobertura.values())
        if cob_min < 25:
            alertas.append(
                f"cobertura_baixa: agente menos visitado cobriu {cob_min:.1f}% dos 2160 estados — "
                "treine mais episódios ou aumente epsilon_inicial."
            )
        td_max = max(info["td_error_recente"]["td_abs_medio"] for info in info_ags.values())
        if td_max > 50 and treino_resumo.get("n_episodios", 0) > 100:
            alertas.append(
                f"td_error_alto: TD-error médio recente {td_max:.1f} — política ainda não convergiu."
            )
        if "n_episodios" not in treino:
            alertas.append("sem_treino: rode train_agents primeiro.")
        if "custo_medio_dia_rs" not in eval_iql and "custo_medio_dia_rs" not in eval_cmp:
            alertas.append("sem_avaliacao: rode evaluate_agents ou compare_strategies.")
        if comparacao and comparacao.get("reducao_iql_vs_sem_pct") is not None \
                and comparacao["reducao_iql_vs_sem_pct"] < 0:
            alertas.append(
                "iql_pior_que_sem_agente: política aprendida custa mais que não fazer nada — "
                "verifique convergência, pesos do reward ou se treino foi suficiente."
            )
        if eval_iql.get("violacoes_pcc_total", 0) > 0:
            alertas.append(f"violacoes_pcc: {eval_iql['violacoes_pcc_total']} horas com importação ≥ PCC.")
        if eval_iql.get("violacoes_soc_total_h", 0) > 0:
            alertas.append(f"violacoes_soc: {eval_iql['violacoes_soc_total_h']} horas com SOC < 15%.")

        pesos_modificados = {
            k: {"atual": CONFIG[k], "default": _DEFAULT_REWARD_WEIGHTS[k]}
            for k in _REWARD_WEIGHT_KEYS
            if abs(CONFIG[k] - _DEFAULT_REWARD_WEIGHTS[k]) > 1e-9
        }
        if pesos_modificados:
            alertas.append(
                f"pesos_reward_modificados: {len(pesos_modificados)} peso(s) diferem do default — "
                "verifique se retreinou após configure_reward_weights."
            )

        return json.dumps({
            "dataset": {
                "fazenda": DATASET_META["id_fazenda"],
                "n_dias": DATASET_META["n_dias"],
                "data_inicio": DATASET_META["data_inicio"],
                "data_fim": DATASET_META["data_fim"],
            },
            "agentes": info_ags,
            "cobertura_pct": cobertura,
            "n_estados_possiveis": N_ESTADOS_TOTAL,
            "soc_propagado_pct": round(float(iql.soc_propagado), 2),
            "treino": treino_resumo,
            "avaliacao_atual": eval_iql,
            "comparacao_baselines": comparacao,
            "pesos_reward_modificados": pesos_modificados or None,
            "alertas": alertas,
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def describe_schema() -> str:
    """Esquema completo: estado, ações, restrições HARD, reward, tarifa, tracker_keys."""
    schema = {
        "arquitetura": "IQL (Independent Q-Learning) com 3 agentes cooperativos",
        "agentes": {
            "armazenamento": {"n_acoes": N_ACOES_ARMAZENAMENTO,
                              "valores": {0: "carregar", 1: "manter", 2: "descarregar"}},
            "consumo":       {"n_acoes": N_ACOES_CONSUMO,
                              "valores": "bitmask 3 bits",
                              "bits": {"bit0(1)": "corta pivô",
                                       "bit1(2)": "corta bomba",
                                       "bit2(4)": "corta secador"}},
            "gerente":       {"n_acoes": N_ACOES_GERENTE,
                              "tetos_kw": TETOS_KW,
                              "valores": {0: "conservador (20kW)",
                                          1: "moderado (30kW)",
                                          2: "liberal (40kW)"}},
        },
        "estado_obs": {
            "hora": "0-23",
            "soc": "0-100 (%)",
            "solar_kw": "kW disponíveis (clipado a inversor 50kW)",
            "eolico_kw": "kW disponíveis (clipado a nominal 10kW)",
            "tarifa": "R$/kWh — 0.68 fora-pico, 1.10 pico (18-20h)",
            "stress": "0-100 — calculado pelo AgenteFinanceiro do env",
            "sec_ac": "kWh acumulados no secador (meta diária 20)",
            "bomba_h": "horas que a bomba já operou (cronograma fixo 8h)",
            "em_pico_tarifa": "bool (tarifa > 0.9)",
            "saldo_creditos_kwh": "saldo de créditos solares (AgenteFinanceiro)",
        },
        "estado_discreto": {
            "tupla": "(h, s, g, st, meta, b)",
            "buckets": {
                "h":    "hora // 6 → 4 valores",
                "s":    "soc // 10 → 10 valores",
                "g":    "solar_kw → 3 (<5 / 5-15 / >15)",
                "st":   "stress → 3 (<30 / 30-70 / >70)",
                "meta": "0/1 (secador atingiu meta diária)",
                "b":    "horas bomba → 3 (<3 / 3-5 / >=6)",
            },
            "n_total": N_ESTADOS_TOTAL,
        },
        "parametros_fisicos": {
            "soc_min_pct": CONFIG["soc_min_pct"],
            "soc_max_pct": CONFIG["soc_max_pct"],
            "soc_inicial_pct": CONFIG["soc_inicial_pct"],
            "bateria_cap_kwh": CONFIG["bateria_cap_kwh"],
            "pcc_max_kw": CONFIG["pcc_max_kw"],
            "inversor_fv_max_kw": CONFIG["inversor_fv_max_kw"],
            "eolico_nominal_kw": CONFIG["eolico_nominal_kw"],
            "pivo_nominal_kw": CONFIG["pivo_nominal_kw"],
            "bomba_cap_nominal_kw": CONFIG["bomba_cap_nominal_kw"],
            "secador_max_kw": CONFIG["secador_max_kw"],
            "secador_meta_kwh": CONFIG["secador_meta_kwh"],
        },
        "restricoes_hard": {
            "R-PIVO":    f"8h consecutivas + 1 ativação/dia (lock automático), "
                         f"{CONFIG['pivo_nominal_kw']} kW durante o lock",
            "R-BOMBA":   f"cronograma fixo nas horas {sorted(BOMBA_HORAS_ON)} — ação do agente é ignorada",
            "R-SECADOR": f"potência da base (coluna secador_kw), meta diária "
                         f"{CONFIG['secador_meta_kwh']} kWh + rescue tardio a "
                         f"{CONFIG['secador_max_kw']} kW se faltar energia",
            "R-SEDE":    f"consumo clampado em ±{int(CONFIG['sede_desvio_max']*100)}% do ideal; "
                         "eco-mode (−20%) em stress ≥ 70",
            "R-PCC":     f"importação/exportação ≤ {CONFIG['pcc_max_kw']} kW",
            "R-BAT":     f"throughput diário ≤ {CONFIG['bat_throughput_max_kwh']} kWh, "
                         f"η carga {CONFIG['eficiencia_carga']}, η descarga {CONFIG['eficiencia_descarga']}",
        },
        "reward_termos": {
            "pen_custo": -CONFIG["w_custo"],
            "pen_estresse": -CONFIG["w_estresse"],
            "pen_soc_critico": -CONFIG["pen_soc"],
            "pen_teto_excedido": -CONFIG["pen_teto"],
            "pen_pcc_violado": -CONFIG["pen_pcc"],
            "pen_kwh_cortado": -CONFIG["pen_producao"],
            "pen_secador_meta_nao_atingida": -CONFIG["pen_secador_meta"],
            "pen_pivo_em_pico": -CONFIG["pen_pivo_pico"],
            "pen_secador_em_pico": -CONFIG["pen_secador_pico"],
            "bonus_pivo_solar": CONFIG["bonus_pivo_solar"],
            "bonus_secador_excedente": CONFIG["bonus_sec_excedente"],
            "bonus_carga_bateria_solar": CONFIG["w_bonus_carga"],
            "bonus_excedente_exportado": CONFIG["bonus_excedente"],
            "bonus_soc_30_80": CONFIG["bonus_soc_ok"],
        },
        "tarifa_tou": {
            "min_rs_kwh": DATASET_META["tarifa_min_rs_kwh"],
            "max_rs_kwh": DATASET_META["tarifa_max_rs_kwh"],
            "horas_pico": DATASET_META["horas_pico"],
        },
        "tracker_keys_validos": ["iql_treino", "iql_eval", "iql_eval_cmp",
                                  "heuristico", "sem_agente", "iql_trace"],
        "info_step_campos": [
            "hora", "soc", "geracao_kw", "consumo_kw", "solar_kw", "eolico_kw",
            "rede_kwh", "excedente", "importacao", "exportacao", "custo_r",
            "tarifa", "reward", "a_arm", "a_cons", "a_ger", "bat_carga", "bat_descarga",
            "pcc_violado", "soc_violado", "fonte_geracao_kwh", "fonte_bateria_kwh",
            "fonte_rede_kwh", "pivo_kw_consumido", "captacao_kw_consumido",
            "sede_kw_consumido", "silo_kw_consumido", "secador_kw_consumido",
            "em_pico_tarifa", "bomba_ligada", "bomba_agendada", "sede_eco",
            "kwh_cortado", "stress", "saldo_creditos_kwh", "teto_excedido",
            "pivo_em_lock", "secador_kwh_ac",
        ],
    }
    return json.dumps(schema, indent=2)


# ------------------------------------------------------------------ #
# Entrada                                                               #
# ------------------------------------------------------------------ #
#
# Por padrão o servidor sobe em transporte HTTP (streamable-http), como
# um processo único e de longa duração que centraliza todo o estado
# (dataset, Q-tables, tracker). O dashboard Streamlit e qualquer cliente
# MCP (Claude Desktop/Code) conectam nesse MESMO processo — não há mais
# caminho que treine ou leia métricas sem passar pelas tools acima.
#
# Use `python server.py --stdio` para o modo clássico de subprocesso
# stdio (um cliente por processo, sem estado compartilhado com o
# dashboard) — mantido só para compatibilidade com clientes que ainda
# não suportam servidores MCP remotos via HTTP.

def main(argv: list[str] | None = None) -> None:
    """Sobe o servidor MCP (chamado pelo `server.py` da raiz do projeto)."""
    argv = sys.argv if argv is None else argv
    usar_stdio = "--stdio" in argv or os.getenv("MCP_TRANSPORT", "streamable-http") == "stdio"
    if usar_stdio:
        mcp.run(transport="stdio")
    else:
        _log(f"Servidor MCP em http://{mcp.settings.host}:{mcp.settings.port}"
             f"{mcp.settings.streamable_http_path} (transporte streamable-http)")
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
