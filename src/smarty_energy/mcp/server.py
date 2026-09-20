"""
MCP Server — SmartEnergy IQL (3 agentes Q-Learning cooperativos).

Expõe ferramentas para configurar, treinar, avaliar e diagnosticar o
sistema multi-agente que espelha o projeto Smart_Energy (FazendaEnergyEnv).

O dataset e carregado explicitamente por initialize(), antes do transporte.
SOC propaga entre episodios (default), refletindo a continuidade entre dias.
"""

import json
import os
import sys

import numpy as np
from mcp.server.fastmcp import FastMCP

from ..config import (
    CONFIG, TETOS_KW, BOMBA_HORAS_ON, ID_FAZENDA, ajustar_decay,
    N_ACOES_ARMAZENAMENTO, N_ACOES_CONSUMO, N_ACOES_GERENTE,
)
from ..data_loader import carregar_dados, descrever_base
from ..environment import FazendaEnergyEnv, ESPACO_ESTADOS_TOTAL as N_ESTADOS_TOTAL
from ..evaluation import identificar_cenarios, classificar_dia
from ..agents import (
    IQLSystem, AgentesHeuristicos, SemAgente, avaliar_politica, construir_agentes,
)
from .. import runs
from . import experiments
from .state import ServerState
from .tracker import MetricsTracker


def _log(msg: str) -> None:
    """Log do servidor — sempre em stderr, para não poluir o canal do protocolo."""
    print(msg, file=sys.stderr)


# ------------------------------------------------------------------ #
# Estado operacional do processo                                       #
# ------------------------------------------------------------------ #

# Episódios por chamada de train_agents. Bem menor que o CONFIG do pipeline
# offline (100k), porque aqui o treino roda dentro de uma tool call; o
# decaimento de ε é reescalado para o horizonte pedido por `ajustar_decay`.
N_EPISODIOS_SERVIDOR = int(os.getenv("MCP_N_EPISODIOS", "1000"))

_state: ServerState | None = None

# ── Braços da comparação — chave do tracker -> rótulo exibido ──────────
# Fonte única dos 4 sistemas comparados; o dashboard reusa estes rótulos.
BRACOS_COMPARACAO = {
    "sem_agente":  "Sem agentes",
    "heuristico":  "Heurísticas",
    "rl_padrao":   "RL padrão",
    "rl_llm_mcp":  "RL + LLM MCP",
}

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
    "bonus_excedente", "bonus_soc_ok", "bonus_descarga_pico",
    "bonus_carga_pico_geracao", "pen_descarga_fora_pico",
    "pen_soc_final", "w_ciclos", "w_pico_demanda",
    "bonus_pivo_solar", "bonus_sec_excedente",
)
_DEFAULT_REWARD_WEIGHTS = {k: CONFIG[k] for k in _REWARD_WEIGHT_KEYS}


def get_state() -> ServerState:
    """Retorna o estado ativo; initialize() deve preceder o uso das tools."""
    if _state is None:
        raise RuntimeError("Servidor nao inicializado; chame initialize() primeiro")
    return _state


def initialize(*, loader=None) -> None:
    """Prepara o estado uma vez; chamadas Python diretas devem inicializar antes.

    O loader opcional fornece (dias, tarifa) sem mudar a selecao de fontes do
    produto. Uma falha na preparacao nao publica estado parcial. Nao oferece
    isolamento entre clientes nem sincronizacao para chamadas concorrentes.
    """
    global _state
    if _state is not None:
        return

    _log("Carregando dataset...")
    dias, tarifa = (carregar_dados if loader is None else loader)()
    meta = descrever_base(dias, tarifa)
    novo_iql = IQLSystem(ajustar_decay(CONFIG, N_EPISODIOS_SERVIDOR))
    novo_heuristico = AgentesHeuristicos(CONFIG)
    novo_sem_agente = SemAgente(CONFIG)
    novo_tracker = MetricsTracker()
    novo_env = FazendaEnergyEnv(dias[0], tarifa, CONFIG)

    _state = ServerState(
        dias=dias, tarifa_24h=tarifa, dataset_meta=meta,
        iql=novo_iql, heuristico=novo_heuristico, sem_agente=novo_sem_agente,
        tracker=novo_tracker, env=novo_env,
    )
    _log(f"  {len(dias)} dias carregados (fazenda {meta['id_fazenda']}).")


def _err(e: Exception) -> str:
    return json.dumps({"erro": f"{type(e).__name__}: {e}"}, indent=2, default=str)


def _congelar_politica(nome: str) -> dict:
    """Copia as Q-tables atuais do IQL sob `nome` em state.snapshots."""
    state = get_state()
    snap = {n: {s: q.copy() for s, q in ag.q_table.items()}
            for n, ag in state.iql.agentes.items()}
    state.snapshots[nome] = snap
    return snap


def _pesos_sao_default() -> bool:
    """True se nenhum peso do reward foi alterado (o LLM-juiz ainda não agiu)."""
    return all(CONFIG[k] == _DEFAULT_REWARD_WEIGHTS[k] for k in _REWARD_WEIGHT_KEYS)


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
        state = get_state()
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

        state.iql.reconfigurar(novos)
        return json.dumps({
            "status": "agentes reconfigurados",
            "hiperparametros_atuais": {n: state.iql.agentes[n].get_info()
                                        for n in state.iql.agentes},
            "n_episodios": state.iql.n_episodios,
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
    bonus_descarga_pico: float | None = None,
    bonus_carga_pico_geracao: float | None = None,
    pen_descarga_fora_pico: float | None = None,
    pen_soc_final: float | None = None,
    w_ciclos: float | None = None,
    w_pico_demanda: float | None = None,
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
        state = get_state()
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
            "bonus_descarga_pico": bonus_descarga_pico,
            "bonus_carga_pico_geracao": bonus_carga_pico_geracao,
            "pen_descarga_fora_pico": pen_descarga_fora_pico,
            "pen_soc_final": pen_soc_final,
            "w_ciclos": w_ciclos,
            "w_pico_demanda": w_pico_demanda,
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
        state.iql.cfg.update(novos)
        # Recria o ambiente ativo para refletir mudancas em step_environment.
        # Treino/avaliação criam env próprio por dia e já usam o CONFIG novo.
        state.env = FazendaEnergyEnv(state.dias[state.dia_atual_idx], state.tarifa_24h, CONFIG)

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
        # Um novo treino invalida as avaliações anteriores. Não mexe em
        # _snapshots["rl_padrao"] quando travado (carregado de um run externo
        # ou congelado manualmente) — só o próprio fluxo de captura automática
        # abaixo decide se recaptura.
        state = get_state()
        state.tracker.limpar("iql_treino")
        for chave in ("iql_eval", "rl_llm_mcp", "rl_padrao", "heuristico", "sem_agente"):
            state.tracker.limpar(chave)
        if n_episodios > 0:
            state.iql.n_episodios = n_episodios
        sumario = state.iql.treinar(state.dias, state.tarifa_24h, FazendaEnergyEnv,
                              tracker=state.tracker, log=_log)
        state.run_carregado = None
        state.experimento_carregado = None
        # RL padrão = treino com os pesos default (sem intervenção do LLM-juiz).
        # Capturado automaticamente para ser o braço de referência da comparação;
        # não sobrescreve um RL padrão carregado de um run externo (travado), nem
        # o snapshot pré-juiz se os pesos já foram alterados.
        if _pesos_sao_default() and not state.rl_padrao_travado:
            _congelar_politica("rl_padrao")
            sumario["rl_padrao_capturado"] = True
        return json.dumps(sumario, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def train_rl_e_mcp(n_episodios: int = 0) -> str:
    """Treina, num só passo, DUAS políticas independentes com o mesmo nº de
    episódios: uma vira o braço 'RL padrão' (congelado e travado) e a outra o
    'RL + LLM MCP' (a política IQL viva que o LLM-juiz pode refinar depois).

    São dois treinos separados (RNGs distintos), então as políticas diferem
    mesmo sem o juiz agir. Use n_episodios=0 para o valor configurado.
    """
    try:
        state = get_state()
        n = n_episodios if n_episodios > 0 else state.iql.n_episodios
        state.experimento_carregado = None

        # 1) RL padrão — IQL independente, treino próprio, congelado e travado.
        rl = IQLSystem(ajustar_decay(CONFIG, n))
        rl.treinar(state.dias, state.tarifa_24h, FazendaEnergyEnv, log=_log)
        state.snapshots["rl_padrao"] = {
            nome: {s: q.copy() for s, q in ag.q_table.items()}
            for nome, ag in rl.agentes.items()
        }
        state.rl_padrao_travado = True

        # 2) RL + LLM MCP — política viva (não recaptura rl_padrao: já travado).
        state.tracker.limpar("iql_treino")
        state.iql.n_episodios = n
        sumario = state.iql.treinar(state.dias, state.tarifa_24h, FazendaEnergyEnv,
                              tracker=state.tracker, log=_log)

        return json.dumps({
            "status": "RL padrão e RL + LLM MCP treinados (independentes)",
            "n_episodios": n,
            "rl_padrao": {
                "best_ep": rl.ultimo_hist["best_ep"],
                "best_custo_med_rs": round(rl.ultimo_hist["best_custo_med"], 2),
                "estados_por_agente": {nm: len(qt) for nm, qt in state.snapshots["rl_padrao"].items()},
            },
            "rl_llm_mcp": {
                "best_ep": sumario.get("best_ep"),
                "custo_medio_ultimos_50_rs": sumario.get("custo_medio_ultimos_50_rs"),
                "epsilon_final": sumario.get("epsilon_final"),
            },
        }, indent=2)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Avaliação                                                             #
# ------------------------------------------------------------------ #

@mcp.tool()
def evaluate_agents(n_dias: int = 30, propagar_soc: bool = True,
                    continuar_do_treino: bool = True) -> str:
    """Avalia o IQL em modo greedy por n_dias percorrendo o dataset.

    propagar_soc=True (default) mantém o SOC final como inicial do próximo
    dia, refletindo continuidade real. False reseta para soc_inicial em
    cada dia (útil para diagnóstico isolado).
    continuar_do_treino=True (default): o 1º dia herda o soc_propagado do
    fim do treino; False parte dos 50% padrão. O SOC final da avaliação
    atualiza o soc_propagado.
    """
    try:
        state = get_state()
        state.tracker.limpar("iql_eval")
        soc_ini = state.iql.soc_propagado if continuar_do_treino else None
        resultado = state.iql.avaliar(
            state.dias, state.tarifa_24h, FazendaEnergyEnv,
            n_dias=n_dias, tracker=state.tracker, propagar_soc=propagar_soc,
            soc_inicial=soc_ini,
        )
        if propagar_soc:
            state.iql.soc_propagado = resultado["soc_final_pct"]
        return json.dumps(resultado, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def compare_strategies(n_dias: int = 30, propagar_soc: bool = True,
                       continuar_do_treino: bool = True) -> str:
    """Compara as 4 estratégias do projeto nos mesmos n_dias do dataset.

    Braços (sempre os 4, mesmas datas e mesmo SOC inicial):
      - Sem agentes  (tracker 'sem_agente')
      - Heurísticas  (tracker 'heuristico')
      - RL padrão    (tracker 'rl_padrao') — política treinada sem o LLM-juiz,
                     capturada automaticamente no train_agents com pesos default.
      - RL + LLM MCP (tracker 'rl_llm_mcp') — política IQL atual (com os ajustes
                     de reward que o LLM-juiz eventualmente aplicou).

    SOC inicial = soc_propagado do treino se continuar_do_treino, senão 50%.
    Enquanto o juiz não agir, 'RL padrão' e 'RL + LLM MCP' coincidem.
    """
    try:
        state = get_state()
        for chave in ("iql_eval", "rl_llm_mcp", "rl_padrao",
                      "heuristico", "sem_agente"):
            state.tracker.limpar(chave)

        soc_ini = state.iql.soc_propagado if continuar_do_treino else None

        # RL + LLM MCP — política IQL atual
        r_llm  = state.iql.avaliar(state.dias, state.tarifa_24h, FazendaEnergyEnv,
                             n_dias=n_dias, tracker=state.tracker,
                             propagar_soc=propagar_soc, soc_inicial=soc_ini)
        # iql escreve em 'iql_eval'; renomeia para o braço da comparação
        state.tracker.passos["rl_llm_mcp"]    = state.tracker.passos.pop("iql_eval", [])
        state.tracker.episodios["rl_llm_mcp"] = state.tracker.episodios.pop("iql_eval", [])

        # RL padrão — snapshot pré-juiz; se ainda não houver, usa a política atual
        # (idêntica ao RL+LLM enquanto o juiz não mexeu nos pesos).
        snap = state.snapshots.get("rl_padrao") or _congelar_politica("rl_padrao")

        def escolher_padrao(env_, est):
            s = env_.discretizar(est)
            acoes = []
            for nome_ag in ("armazenamento", "consumo", "gerente"):
                q = snap[nome_ag].get(s)
                acoes.append(int(q.argmax()) if q is not None else 0)
            return tuple(acoes)

        r_padrao = avaliar_politica(
            escolher_padrao, state.dias, state.tarifa_24h, cfg=CONFIG,
            env_cls=FazendaEnergyEnv, n_dias=n_dias, tracker=state.tracker,
            tracker_key="rl_padrao", propagar_soc=propagar_soc,
            soc_inicial=soc_ini,
        )

        r_heur = state.heuristico.avaliar(state.dias, state.tarifa_24h, FazendaEnergyEnv,
                                     n_dias=n_dias, tracker=state.tracker,
                                     tracker_key="heuristico",
                                     propagar_soc=propagar_soc,
                                     soc_inicial=soc_ini)
        r_sem  = state.sem_agente.avaliar(state.dias, state.tarifa_24h, FazendaEnergyEnv,
                                     n_dias=n_dias, tracker=state.tracker,
                                     tracker_key="sem_agente",
                                     propagar_soc=propagar_soc,
                                     soc_inicial=soc_ini)

        resultados = {
            "SemAgente":  r_sem,
            "Heuristico": r_heur,
            "RL_padrao":  r_padrao,
            "RL_LLM_MCP": r_llm,
            "tracker_keys": ["sem_agente", "heuristico", "rl_padrao", "rl_llm_mcp"],
            "rotulos": BRACOS_COMPARACAO,
        }

        custo_sem  = r_sem["custo_medio_dia_rs"]
        custo_heur = r_heur["custo_medio_dia_rs"]
        custo_pad  = r_padrao["custo_medio_dia_rs"]
        custo_llm  = r_llm["custo_medio_dia_rs"]

        # Reduções da política final (RL + LLM MCP) frente às referências.
        if custo_sem > 0:
            resultados["reducao_rl_llm_vs_sem_pct"] = round(
                (custo_sem - custo_llm) / custo_sem * 100, 2)
        if custo_heur > 0:
            resultados["reducao_rl_llm_vs_heur_pct"] = round(
                (custo_heur - custo_llm) / custo_heur * 100, 2)
        # Reduções do RL padrão (sem LLM) — mesma base, para comparar os dois RL.
        if custo_sem > 0:
            resultados["reducao_rl_padrao_vs_sem_pct"] = round(
                (custo_sem - custo_pad) / custo_sem * 100, 2)
        # Ganho do LLM-juiz sobre o RL padrão.
        if custo_pad > 0:
            resultados["reducao_llm_vs_rl_padrao_pct"] = round(
                (custo_pad - custo_llm) / custo_pad * 100, 2)

        return json.dumps(resultados, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def run_episode(mode: str = "eval", dia_idx: int | None = None,
                continuar_soc: bool = True, policy: str = "rl_llm_mcp") -> str:
    """Executa 1 dia completo e retorna o trace hora-a-hora.

    mode: "eval" (greedy) ou "train" (ε-greedy com aprendizado online)
    dia_idx: índice do dia no dataset (None = dia atual selecionado)
    continuar_soc: True (default) encadeia o SOC — o dia começa com o SOC
        final da última run_episode (continuidade da bateria); a primeira
        chamada parte do soc_propagado do IQL (50% se nunca treinou).
        False reinicia a cadeia a partir do soc_propagado.
    policy: "rl_llm_mcp" (default) usa a política IQL viva (treinável, reflete o
        LLM-juiz). Qualquer outro valor é tratado como nome de um snapshot
        congelado em state.snapshots (ex.: "rl_padrao" = RL sem o juiz): roda sempre
        greedy, ignora `mode`, não aprende e mantém uma cadeia de SOC própria,
        para não se misturar com a da política viva ao alternar no dashboard.
    """
    try:
        state = get_state()
        idx = state.dia_atual_idx if dia_idx is None else int(dia_idx)
        if not (0 <= idx < len(state.dias)):
            return json.dumps({"erro": f"dia_idx fora do range [0, {len(state.dias)-1}]"}, indent=2)

        usar_snapshot = policy not in ("rl_llm_mcp", "atual")
        if usar_snapshot and policy not in state.snapshots:
            return json.dumps({"erro": f"snapshot '{policy}' não existe — treine "
                               "com os pesos default (captura o 'rl_padrao') ou "
                               "carregue-o com carregar_rl_padrao primeiro."}, indent=2)
        snap = state.snapshots.get(policy) if usar_snapshot else None

        state.tracker.limpar("iql_trace")
        e = FazendaEnergyEnv(state.dias[idx], state.tarifa_24h, CONFIG)
        soc_prev = state.soc_trace_snapshot if usar_snapshot else state.soc_trace
        soc_ini = (soc_prev if (continuar_soc and soc_prev is not None)
                   else state.iql.soc_propagado)
        est = e.reset(soc_inicial=soc_ini)
        s = e.discretizar(est)

        # Snapshot é frozen: nunca explora nem aprende, mesmo em mode='train'.
        explore = (mode == "train") and not usar_snapshot
        reward_total = 0.0
        custo_total  = 0.0

        def _acoes_snapshot(s_disc):
            acoes = []
            for nome_ag in ("armazenamento", "consumo", "gerente"):
                q = snap[nome_ag].get(s_disc)
                acoes.append(int(q.argmax()) if q is not None else 0)
            return tuple(acoes)

        for _ in range(24):
            acoes = (_acoes_snapshot(s) if usar_snapshot
                     else state.iql.agir_todos(s, explorando=explore))
            prox, reward, done, info = e.step(*acoes)
            s2 = e.discretizar(prox)
            if explore:
                state.iql.aprender_todos(s, acoes, reward, s2, done)
            s = s2
            state.tracker.registrar_passo(info, agente="iql_trace")
            reward_total += reward
            custo_total  += info["custo_r"]

        if usar_snapshot:
            state.soc_trace_snapshot = float(e.soc)
        else:
            state.soc_trace = float(e.soc)
        return json.dumps({
            "mode": "eval" if usar_snapshot else mode,
            "policy": policy,
            "dia_idx": idx,
            "data": state.dataset_meta.get("data_inicio") if idx == 0 else str(state.dias[idx]["data"].iloc[0])[:10],
            "cenario": classificar_dia(idx, state.dias),
            "soc_inicial_pct": round(float(soc_ini), 2),
            "reward_total": round(reward_total, 4),
            "custo_total_rs": round(custo_total, 4),
            "soc_final_pct": round(e.soc, 2),
            "trace": state.tracker.get_trace_ultimo_episodio("iql_trace"),
        }, indent=2, default=str)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Métricas                                                              #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_training_metrics() -> str:
    """Métricas do último treino: rewards/custos/epsilons + info dos 3 agentes."""
    state = get_state()
    return json.dumps({
        "treino": state.tracker.get_training_metrics("iql_treino"),
        "agentes": {n: ag.get_info() for n, ag in state.iql.agentes.items()},
    }, indent=2)


@mcp.tool()
def get_qtables_info() -> str:
    """Estatísticas das Q-tables dos 3 agentes IQL."""
    state = get_state()
    return json.dumps({n: ag.get_info() for n, ag in state.iql.agentes.items()}, indent=2)


@mcp.tool()
def get_td_error_series(agente: str = "armazenamento") -> str:
    """Série completa de TD-error (janela rolante de até 5000 updates) de 1 agente.

    Usado pelo dashboard para plotar a curva de convergência por agente —
    `get_qtables_info` só traz o resumo (`td_error_recente`), não a série.

    agente: "armazenamento", "consumo" ou "gerente".
    """
    try:
        state = get_state()
        if agente not in state.iql.agentes:
            return json.dumps({
                "erro": f"agente inválido: {agente}. Use um de {list(state.iql.agentes)}",
            }, indent=2)
        ag = state.iql.agentes[agente]
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
    state = get_state()
    return json.dumps(state.tracker.get_learning_curve("iql_treino",
                                                  janela=janela_media_movel), indent=2)


@mcp.tool()
def get_eval_metrics(agente: str = "iql_eval") -> str:
    """Métricas da última avaliação.

    `agente`: "iql_eval" (default), "rl_llm_mcp", "rl_padrao", "heuristico", "sem_agente".
    """
    state = get_state()
    return json.dumps(state.tracker.get_eval_metrics(agente), indent=2)


@mcp.tool()
def get_peak_offpeak_stats(agente: str = "iql_eval") -> str:
    """Consumo por carga separado por período tarifário (pico vs fora-pico)."""
    state = get_state()
    return json.dumps(state.tracker.get_peak_offpeak_stats(agente), indent=2)


@mcp.tool()
def get_battery_dispatch_stats(agente: str = "iql_eval") -> str:
    """Carga/descarga da bateria por tarifa e motivos de descarga bloqueada."""
    state = get_state()
    return json.dumps(state.tracker.get_battery_dispatch_stats(agente), indent=2)


@mcp.tool()
def get_stats_por_cenario(agente: str = "iql_eval") -> str:
    """Reward/custo médio por cenário climático (NUBLADO/ENSOLARADO/ALTO CONSUMO/EQUILIBRADO).

    Como o env real não classifica cenário automaticamente, o tracker
    armazena 'REAL'; para uma análise por cenário use identify_scenarios
    com um trace específico.
    """
    state = get_state()
    return json.dumps(state.tracker.get_stats_por_cenario(agente), indent=2)


@mcp.tool()
def get_hourly_violations(agente: str = "iql_eval") -> str:
    """Violações (SOC, PCC, teto) agregadas por hora-do-dia.

    Útil para o LLM-juiz identificar em quais horas a política falha mais.
    """
    state = get_state()
    return json.dumps(state.tracker.get_hourly_violations(agente), indent=2)


@mcp.tool()
def get_equipment_hourly(agente: str = "iql_eval") -> str:
    """Uso médio por hora-do-dia de cada equipamento (kW), agregando dias.

    Retorna pivô, captação, secador, sede, silo + bateria (carga/descarga),
    rede e geração médias por hora 0-23.

    `agente`: "iql_eval", "rl_llm_mcp", "rl_padrao", "heuristico", "sem_agente", "iql_trace".
    """
    state = get_state()
    return json.dumps(state.tracker.get_equipment_hourly(agente), indent=2)


@mcp.tool()
def get_equipment_stats(agente: str = "iql_eval") -> str:
    """KPIs por equipamento (lógica de BI) da última avaliação/comparação.

    Por equipamento: kWh total e médio/dia, horas ligada, kWh em pico,
    % do consumo total e custo bruto da energia (kWh × tarifa da hora).

    `agente`: "iql_eval", "rl_llm_mcp", "rl_padrao", "heuristico", "sem_agente", "iql_trace".
    """
    state = get_state()
    return json.dumps(state.tracker.get_equipment_stats(agente), indent=2)


@mcp.tool()
def export_all_data() -> str:
    """Exporta em um único JSON todos os dados do servidor: dataset, config,
    Q-tables (resumo), treino, curva de aprendizado, avaliações de todas as
    estratégias, violações por hora e KPIs de equipamentos.

    Pensado para o botão "Exportar dados" do dashboard — o payload pode ser
    salvo direto em arquivo.
    """
    try:
        state = get_state()
        from datetime import datetime, timezone

        chaves_eval = ("iql_eval", "rl_llm_mcp", "rl_padrao",
                       "heuristico", "sem_agente")

        def _se_tem(d: dict) -> dict | None:
            return None if (not d or "aviso" in d) else d

        return json.dumps({
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "dataset": state.dataset_meta,
            "config": {k: (sorted(v) if isinstance(v, frozenset) else v)
                       for k, v in CONFIG.items()},
            "tetos_kw": TETOS_KW,
            "bomba_horas_on": sorted(BOMBA_HORAS_ON),
            "agentes": {n: ag.get_info() for n, ag in state.iql.agentes.items()},
            "soc_propagado_pct": round(float(state.iql.soc_propagado), 2),
            "treino": _se_tem(state.tracker.get_training_metrics("iql_treino")),
            "curva_aprendizado": _se_tem(state.tracker.get_learning_curve("iql_treino")),
            "avaliacoes": {k: _se_tem(state.tracker.get_eval_metrics(k))
                           for k in chaves_eval},
            "violacoes_por_hora": {k: _se_tem(state.tracker.get_hourly_violations(k))
                                   for k in chaves_eval},
            "equipamentos_kpis": {k: _se_tem(state.tracker.get_equipment_stats(k))
                                  for k in chaves_eval},
            "equipamentos_hora_a_hora": {k: _se_tem(state.tracker.get_equipment_hourly(k))
                                         for k in chaves_eval},
        }, indent=2, default=str)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Cenários e dataset                                                    #
# ------------------------------------------------------------------ #

@mcp.tool()
def identify_scenarios() -> str:
    """Índices dos 3 dias extremos do dataset (nublado/ensolarado/alto_consumo)."""
    state = get_state()
    cen = identificar_cenarios(state.dias)
    enriquecido = {}
    for nome, idx in cen.items():
        dia = state.dias[idx]
        enriquecido[nome] = {
            "dia_idx": idx,
            "data": str(dia["data"].iloc[0])[:10],
            "geracao_total_kwh": round(float(dia["solar_kw"].sum() + dia["eolico_kw"].sum()), 2),
            "consumo_total_kwh": round(float((dia["pivo_kw"] + dia["captacao_kw"]
                                              + dia["sede_kw"] + dia["silo_kw"]).sum()), 2),
            "categoria": classificar_dia(idx, state.dias),
        }
    return json.dumps(enriquecido, indent=2)


@mcp.tool()
def get_dataset_info() -> str:
    """Informações sobre o dataset carregado (fazenda, n_dias, range de datas, tarifa)."""
    state = get_state()
    return json.dumps({
        **state.dataset_meta,
        "tarifa_horaria_rs_kwh": [round(float(t), 4) for t in state.tarifa_24h],
        "horas_pico_tarifa": [int(h) for h in range(24) if state.tarifa_24h[h] > 0.9],
    }, indent=2)


@mcp.tool()
def switch_dataset(dataset_dir: str, id_fazenda: str = "", mes: int = 1) -> str:
    """Troca a fazenda ativa do servidor por um dataset Parquet do FEMS.

    Aponta o servidor para outra pasta gerada por `gerar_dataset.py --completo`
    (outra fazenda ou outro mês/ano). É um RESET COMPLETO: políticas, snapshots,
    tracker e avaliações são descartados — uma fazenda nova é um problema novo.
    Modelos salvos (experimentos) NÃO são afetados; note que carregar um modelo
    treinado em outra fazenda produz comparação inválida (o load avisa).

    Args:
        dataset_dir : pasta com consumo/geracao/consumo_fatura.parquet
        id_fazenda  : id dentro do dataset (vazio = usa o ID_FAZENDA do config)
        mes         : 1-12 recorta um mês; 0 usa a série inteira
    """
    try:
        state = get_state()
        from ..data_loader import _carregar_fems
        from ..config import ID_FAZENDA as _ID_DEFAULT
        fid = id_fazenda.strip() or _ID_DEFAULT

        dias_novos, tarifa_nova = _carregar_fems(dataset_dir, mes=mes,
                                                 id_fazenda=fid)

        state.dias, state.tarifa_24h = dias_novos, tarifa_nova
        state.dataset_meta = {**descrever_base(state.dias, state.tarifa_24h, id_fazenda=fid),
                        "fonte": f"FEMS ({dataset_dir})"}

        # Reset completo do estado de análise — nova fazenda, novo problema.
        state.iql = IQLSystem(ajustar_decay(CONFIG, N_EPISODIOS_SERVIDOR))
        state.snapshots.clear()
        state.rl_padrao_travado = False
        state.run_carregado = None
        state.experimento_carregado = None
        state.dia_atual_idx = 0
        state.soc_trace = None
        state.soc_trace_snapshot = None
        for chave in ("iql_treino", "iql_eval", "iql_trace", "rl_llm_mcp",
                      "rl_padrao", "heuristico", "sem_agente"):
            state.tracker.limpar(chave)
        state.env = FazendaEnergyEnv(state.dias[state.dia_atual_idx], state.tarifa_24h, CONFIG)

        return json.dumps({
            "status": "dataset trocado — estado de análise zerado",
            **state.dataset_meta,
            "proximo_passo": "train_rl_e_mcp (ou load_experiment de um modelo "
                             "desta mesma fazenda).",
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def select_day(dia_idx: int) -> str:
    """Seleciona um dia específico do dataset para get_current_state / step_environment."""
    try:
        state = get_state()
        if not (0 <= dia_idx < len(state.dias)):
            return json.dumps({"erro": f"dia_idx fora de [0, {len(state.dias)-1}]"}, indent=2)
        state.dia_atual_idx = dia_idx
        state.env = FazendaEnergyEnv(state.dias[dia_idx], state.tarifa_24h, CONFIG)
        return json.dumps({
            "status": "dia selecionado",
            "dia_idx": dia_idx,
            "data": str(state.dias[dia_idx]["data"].iloc[0])[:10],
            "categoria": classificar_dia(dia_idx, state.dias),
        }, indent=2)
    except Exception as e:
        return _err(e)


# ------------------------------------------------------------------ #
# Ambiente                                                              #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_current_state() -> str:
    """Estado atual do env (dia selecionado, hora corrente)."""
    state = get_state()
    return json.dumps({
        "dia_idx": state.dia_atual_idx,
        "data": str(state.dias[state.dia_atual_idx]["data"].iloc[0])[:10],
        **{k: (round(float(v), 4) if isinstance(v, (int, float)) else v)
           for k, v in state.env.get_full_state().items()},
    }, indent=2)


@mcp.tool()
def reset_environment(reset_agents: bool = False, dia_idx: int | None = None) -> str:
    """Reinicia o env (e opcionalmente as Q-tables).

    Se dia_idx for fornecido, troca o dia selecionado. SOC inicial vem do
    soc_propagado mantido pelo IQLSystem.
    """
    try:
        state = get_state()
        if dia_idx is not None:
            if not (0 <= dia_idx < len(state.dias)):
                return json.dumps({"erro": f"dia_idx fora de [0, {len(state.dias)-1}]"}, indent=2)
            state.dia_atual_idx = dia_idx
        state.env = FazendaEnergyEnv(state.dias[state.dia_atual_idx], state.tarifa_24h, CONFIG)
        state.env.reset(soc_inicial=state.iql.soc_propagado)
        state.soc_trace = None
        state.soc_trace_snapshot = None

        if reset_agents:
            state.iql.reset_qtables()
            state.tracker.limpar()

        return json.dumps({
            "status": "ambiente reiniciado",
            "agentes_reiniciados": reset_agents,
            "dia_idx": state.dia_atual_idx,
            "estado": {k: (round(float(v), 4) if isinstance(v, (int, float)) else v)
                       for k, v in state.env.get_full_state().items()},
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
        state = get_state()
        est = state.env._estado()
        s = state.env.discretizar(est)
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

    a_arm: 0=solar, 1=manter, 2/3/4=descarregar 25/50/100%, 5=carregar pela rede
    a_cons: bitmask 3 bits (bit0=corta pivô, bit1=corta bomba, bit2=corta secador)
    a_ger: 0=conservador(20kW), 1=moderado(30kW), 2=liberal(40kW)
    """
    try:
        state = get_state()
        if not (0 <= a_arm < N_ACOES_ARMAZENAMENTO):
            return json.dumps({"erro": f"a_arm inválido: {a_arm}"}, indent=2)
        if not (0 <= a_cons <= 7):
            return json.dumps({"erro": f"a_cons inválido: {a_cons}"}, indent=2)
        if a_ger not in (0, 1, 2):
            return json.dumps({"erro": f"a_ger inválido: {a_ger}"}, indent=2)

        prox, reward, done, info = state.env.step(a_arm, a_cons, a_ger)
        s2 = state.env.discretizar(prox)
        return json.dumps({
            "reward": round(reward, 6),
            "done": done,
            "next_state_discrete": list(s2),
            "obs": {k: (bool(v) if isinstance(v, (bool, np.bool_)) else
                        round(float(v), 4) if isinstance(v, (int, float)) else v)
                    for k, v in prox.items()},
            "info": {k: (bool(v) if isinstance(v, (bool, np.bool_)) else
                         round(float(v), 6) if isinstance(v, (int, float)) else v)
                     for k, v in info.items()},
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_actions(explore: bool = False) -> str:
    """Ações escolhidas pelos 3 agentes IQL para o estado atual + Q-values."""
    try:
        state = get_state()
        est = state.env._estado()
        s = state.env.discretizar(est)
        out = {"state_discrete": list(s)}
        for nome, ag in state.iql.agentes.items():
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
        state = get_state()
        if dir_path:
            state.iql.save_all(dir_path)
            return json.dumps({
                "status": "Q-tables salvas",
                "dir": dir_path,
                "arquivos": [f"qtable_{n}.pkl" for n in state.iql.agentes],
            }, indent=2)

        if state.iql.ultimo_hist is None:
            return json.dumps({
                "erro": "nenhum treino nesta sessão — rode train_agents() antes, "
                        "ou informe dir_path para salvar só os pickles.",
            }, indent=2)

        run_id = runs.salvar_run(state.iql.agentes, state.iql.ultimo_hist,
                                 fonte_dados=f"MCP · {state.dataset_meta['id_fazenda']}")
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
        state = get_state()
        if dir_path:
            state.iql.load_all(dir_path)
            origem = dir_path
            hist = None
        else:
            rid = run_id or runs.run_mais_recente()
            if rid is None:
                return json.dumps({"erro": "nenhum run em outputs/runs/"}, indent=2)
            hist = runs.carregar_run(rid, state.iql.agentes)
            origem = rid
        if hist is not None:
            state.iql.ultimo_hist = hist
            state.iql.soc_propagado = float(hist.get("soc_final_pct", state.iql.soc_propagado))
        state.run_carregado = {
            "origem": origem,
            "n_episodios": hist.get("n_episodios") if hist else None,
        }
        return json.dumps({
            "status": "Q-tables carregadas",
            "origem": origem,
            "n_episodios": state.run_carregado["n_episodios"],
            "agentes": {n: ag.get_info() for n, ag in state.iql.agentes.items()},
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_financeiro_state() -> str:
    """Estado atual do AgenteFinanceiro do env: saldo de créditos + estresse atual."""
    try:
        state = get_state()
        est = state.env._estado()
        return json.dumps({
            "saldo_creditos_kwh": round(float(state.env.fin.saldo_creditos), 4),
            "estresse_atual": round(float(est["stress"]), 2),
            "tarifa_atual_rs_kwh": round(float(est["tarifa"]), 4),
            "em_pico_tarifa": est["em_pico_tarifa"],
            "credito_inicial_kwh": CONFIG["credito_inicial_kwh"],
            "tarifa_estresse_limiar_rs_kwh": CONFIG["tarifa_estresse_limiar"],
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def snapshot_policy(nome: str = "rl_padrao") -> str:
    """Congela a política IQL atual (cópia das Q-tables) sob um nome.

    O braço 'RL padrão' da comparação já é capturado automaticamente no
    train_agents (com pesos default). Use esta tool só para sobrescrever
    manualmente esse snapshot, ou para congelar sob outro nome. Congelar
    sob "rl_padrao" trava o snapshot (como `carregar_rl_padrao`): só
    `liberar_rl_padrao()` permite que train_agents volte a recapturá-lo.
    """
    try:
        state = get_state()
        snap = _congelar_politica(nome)
        if nome == "rl_padrao":
            state.rl_padrao_travado = True
        return json.dumps({
            "status": "política congelada",
            "nome": nome,
            "estados_por_agente": {n: len(qt) for n, qt in snap.items()},
            "uso": "vira o braço 'RL padrão' de compare_strategies (travado)"
                   if nome == "rl_padrao" else None,
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def carregar_rl_padrao(dir_path: str = "", run_id: str = "") -> str:
    """Define o braço 'RL padrão' a partir de um run treinado (ex.: Smart_Energy).

    Carrega as 3 Q-tables do run em agentes próprios e as congela como o
    snapshot 'rl_padrao' — SEM tocar na política IQL viva (o braço RL + LLM
    MCP). Assim o 'RL padrão' fica idêntico ao RL do projeto Smart_Energy.
    O snapshot fica TRAVADO: train_agents não o sobrescreve até chamar
    `liberar_rl_padrao()`.

    Args:
        dir_path : pasta de um run (com qtable_<agente>.pkl) OU a pasta de runs
                   que contém vários runs — nesse caso pega o mais recente com
                   as 3 Q-tables. Tem prioridade sobre run_id.
        run_id   : id de um run em outputs/runs/ do próprio MCP.
    """
    try:
        state = get_state()
        agentes = construir_agentes(CONFIG)
        if dir_path:
            from pathlib import Path
            base = Path(dir_path)
            # Se não há Q-tables direto na pasta, trata como pasta de RUNS e
            # resolve para o run mais recente (nomes por timestamp ordenáveis).
            if not (base / "qtable_consumo.pkl").exists():
                candidatos = sorted(
                    d for d in base.glob("*") if (d / "qtable_consumo.pkl").exists()
                )
                if not candidatos:
                    return json.dumps(
                        {"erro": f"nenhum run com qtable_*.pkl em {base} "
                                 "(nem na pasta, nem em subpastas)"}, indent=2)
                base = candidatos[-1]
            for nome, ag in agentes.items():
                p = base / f"qtable_{nome}.pkl"
                if not p.exists():
                    return json.dumps({"erro": f"não encontrei {p}"}, indent=2)
                ag.load(p)
            origem = str(base)
        else:
            rid = run_id or runs.run_mais_recente()
            if rid is None:
                return json.dumps({"erro": "nenhum run em outputs/runs/"}, indent=2)
            runs.carregar_run(rid, agentes)
            origem = rid

        state.snapshots["rl_padrao"] = {
            n: {s: q.copy() for s, q in ag.q_table.items()}
            for n, ag in agentes.items()
        }
        state.rl_padrao_travado = True
        return json.dumps({
            "status": "RL padrão carregado e travado",
            "origem": origem,
            "estados_por_agente": {n: len(qt) for n, qt in state.snapshots["rl_padrao"].items()},
            "nota": "rode compare_strategies para incluí-lo; train_agents não o sobrescreve.",
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def liberar_rl_padrao() -> str:
    """Destrava o 'RL padrão' — o próximo train_agents volta a capturá-lo."""
    state = get_state()
    state.rl_padrao_travado = False
    return json.dumps({"status": "RL padrão destravado",
                       "nota": "o próximo train_agents (pesos default) recaptura o snapshot."},
                      indent=2)


# ------------------------------------------------------------------ #
# Experimentos — modelos salvos (par RL padrão + RL + LLM MCP)          #
# ------------------------------------------------------------------ #

@mcp.tool()
def save_experiment(label: str = "") -> str:
    """Salva o estado treinado como um 'modelo' reutilizável (experimento).

    Congela em outputs/experimentos/<exp_id>/ os DOIS braços — a política
    viva 'RL + LLM MCP' e o snapshot 'RL padrão' — com os pesos do reward
    vigentes e metadados. Depois, load_experiment restaura tudo sem retreinar.

    `label` vazio vira "<n_episodios>ep" (ex.: "50000ep"); renomeável depois
    com rename_experiment.
    """
    try:
        state = get_state()
        if not any(ag.q_table for ag in state.iql.agentes.values()):
            return json.dumps({"erro": "nenhuma política treinada — rode "
                                       "train_agents/train_rl_e_mcp antes."}, indent=2)
        snap = state.snapshots.get("rl_padrao") or _congelar_politica("rl_padrao")

        custos = {}
        for chave in ("rl_padrao", "rl_llm_mcp"):
            m = state.tracker.get_eval_metrics(chave)
            if "custo_medio_dia_rs" in m:
                custos[chave] = round(m["custo_medio_dia_rs"], 2)

        exp_id = experiments.salvar(
            state.iql.agentes, snap,
            label=label,
            hist=state.iql.ultimo_hist,
            pesos_reward={k: CONFIG[k] for k in _REWARD_WEIGHT_KEYS},
            fonte_dados=state.dataset_meta.get("fonte"),
            soc_propagado=state.iql.soc_propagado,
            rl_padrao_travado=state.rl_padrao_travado,
            custos=custos,
        )
        meta = experiments._ler_meta(exp_id)
        return json.dumps({
            "status": "experimento salvo",
            "exp_id": exp_id,
            "label": meta["label"],
            "caminho": str(experiments.caminho(exp_id)),
            "custos": custos,
            "nota": "load_experiment restaura os 2 braços sem retreinar.",
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def load_experiment(exp_id: str = "") -> str:
    """Restaura um experimento salvo — pula a etapa de treino.

    Recarrega a política viva (RL + LLM MCP), o snapshot 'RL padrão'
    (travado), os pesos do reward e o SOC propagado. Depois disso basta
    compare_strategies para medir — sem retreinar. `exp_id` vazio usa o
    mais recente. Avaliações anteriores são descartadas (eram de outra
    política).
    """
    try:
        state = get_state()
        eid = exp_id or experiments.mais_recente()
        if eid is None:
            return json.dumps({"erro": "nenhum experimento salvo em "
                                       f"{experiments.EXP_DIR}"}, indent=2)

        snap, meta, hist = experiments.carregar(eid, state.iql.agentes)
        state.snapshots["rl_padrao"] = snap
        state.rl_padrao_travado = True

        pesos = meta.get("pesos_reward") or {}
        if pesos:
            CONFIG.update(pesos)
            state.iql.cfg.update(pesos)
            state.env = FazendaEnergyEnv(state.dias[state.dia_atual_idx], state.tarifa_24h, CONFIG)

        if meta.get("soc_propagado_pct") is not None:
            state.iql.soc_propagado = float(meta["soc_propagado_pct"])
        if hist is not None:
            state.iql.ultimo_hist = hist

        for chave in ("iql_treino", "iql_eval", "rl_llm_mcp", "rl_padrao",
                      "heuristico", "sem_agente"):
            state.tracker.limpar(chave)

        state.run_carregado = {"origem": f"experimento:{eid}",
                          "n_episodios": meta.get("n_episodios")}
        state.experimento_carregado = {"exp_id": eid, "label": meta.get("label")}

        avisos = experiments.avisos_fisica(meta)
        fonte_exp = meta.get("fonte_dados")
        if fonte_exp and fonte_exp != state.dataset_meta.get("fonte"):
            avisos.append(
                f"modelo treinado em outra fonte de dados ({fonte_exp}) — "
                f"a fazenda ativa é {state.dataset_meta.get('fonte')}; a comparação "
                "não é válida entre fazendas diferentes."
            )

        return json.dumps({
            "status": "experimento carregado — treino dispensado",
            "exp_id": eid,
            "label": meta.get("label"),
            "n_episodios": meta.get("n_episodios"),
            "pesos_restaurados": bool(pesos),
            "custos_salvos": meta.get("custos", {}),
            "avisos_fisica": avisos,
            "proximo_passo": "compare_strategies para medir os 4 braços.",
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def list_experiments() -> str:
    """Lista os modelos salvos (mais recente primeiro): id, label, episódios,
    pesos alterados vs default e custos registrados na época."""
    try:
        itens = []
        for m in experiments.listar():
            pesos = m.get("pesos_reward") or {}
            delta = {k: v for k, v in pesos.items()
                     if k in _DEFAULT_REWARD_WEIGHTS and v != _DEFAULT_REWARD_WEIGHTS[k]}
            itens.append({
                "exp_id": m["exp_id"],
                "label": m.get("label"),
                "criado_em": m.get("criado_em"),
                "n_episodios": m.get("n_episodios"),
                "custos": m.get("custos", {}),
                "pesos_alterados": delta,
                "fonte_dados": m.get("fonte_dados"),
            })
        return json.dumps({"n": len(itens), "experimentos": itens}, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def rename_experiment(exp_id: str, novo_label: str) -> str:
    """Renomeia um modelo salvo (troca o label amigável; o exp_id não muda)."""
    try:
        meta = experiments.renomear(exp_id, novo_label.strip())
        return json.dumps({"status": "renomeado", "exp_id": exp_id,
                           "label": meta["label"]}, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_analysis_status() -> str:
    """Estado operacional da análise para interfaces: etapas concluídas e próxima ação.

    'avaliado' e 'comparado' refletem a mesma medição — desde que
    compare_strategies passou a ser o único passo de avaliação do dashboard,
    os dois ficam sempre iguais (fonte: braço 'rl_llm_mcp').
    """
    try:
        state = get_state()
        treino = state.tracker.get_training_metrics("iql_treino")
        avaliacao = state.tracker.get_eval_metrics("rl_llm_mcp")

        treinado = "n_episodios" in treino or state.run_carregado is not None
        avaliado = "custo_medio_dia_rs" in avaliacao
        comparado = avaliado
        rl_padrao_congelado = "rl_padrao" in state.snapshots

        if not treinado:
            proxima_etapa = "treinar"
        elif not comparado:
            proxima_etapa = "comparar"
        else:
            proxima_etapa = "investigar"

        return json.dumps({
            "treinado": treinado,
            "avaliado": avaliado,
            "comparado": comparado,
            "rl_padrao_congelado": rl_padrao_congelado,
            "rl_padrao_travado": state.rl_padrao_travado,
            "proxima_etapa": proxima_etapa,
            "n_episodios": treino.get("n_episodios") or state.run_carregado.get("n_episodios") if state.run_carregado else treino.get("n_episodios"),
            "n_dias_avaliados": avaliacao.get("n_dias"),
            "run_carregado": state.run_carregado,
            "experimento_carregado": state.experimento_carregado,
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
        state = get_state()
        info_ags = {n: ag.get_info() for n, ag in state.iql.agentes.items()}
        cobertura = {n: round(info["n_estados_visitados"] / N_ESTADOS_TOTAL * 100, 2)
                     for n, info in info_ags.items()}

        treino = state.tracker.get_training_metrics("iql_treino")
        treino_resumo = {k: v for k, v in treino.items()
                         if k not in ("rewards_hist", "custos_hist", "epsilons")}

        # 'rl_llm_mcp' (populado por compare_strategies) é a ÚNICA fonte da
        # avaliação da política atual — evita a duplicidade com 'iql_eval'
        # (que exigia rodar evaluate_agents à parte para o mesmo resultado).
        eval_cmp  = state.tracker.get_eval_metrics("rl_llm_mcp")
        eval_puro = state.tracker.get_eval_metrics("rl_padrao")
        eval_heur = state.tracker.get_eval_metrics("heuristico")
        eval_sem  = state.tracker.get_eval_metrics("sem_agente")

        comparacao = None
        if all("custo_medio_dia_rs" in m for m in (eval_cmp, eval_heur, eval_sem)):
            c_llm, c_heur, c_sem = (m["custo_medio_dia_rs"] for m in (eval_cmp, eval_heur, eval_sem))
            comparacao = {
                "custo_rl_llm_mcp_rs_dia": round(c_llm, 4),
                "custo_heuristico_rs_dia": round(c_heur, 4),
                "custo_sem_agente_rs_dia": round(c_sem, 4),
                "reducao_rl_llm_vs_sem_pct":  round((c_sem - c_llm) / c_sem * 100, 2) if c_sem > 0 else None,
                "reducao_rl_llm_vs_heur_pct": round((c_heur - c_llm) / c_heur * 100, 2) if c_heur > 0 else None,
            }
            if "custo_medio_dia_rs" in eval_puro:
                c_pad = eval_puro["custo_medio_dia_rs"]
                comparacao["custo_rl_padrao_rs_dia"] = round(c_pad, 4)
                comparacao["reducao_rl_padrao_vs_sem_pct"] = (
                    round((c_sem - c_pad) / c_sem * 100, 2) if c_sem > 0 else None)
                comparacao["reducao_llm_vs_rl_padrao_pct"] = (
                    round((c_pad - c_llm) / c_pad * 100, 2) if c_pad > 0 else None)

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
        if "custo_medio_dia_rs" not in eval_cmp:
            alertas.append("sem_avaliacao: rode compare_strategies.")
        if comparacao and comparacao.get("reducao_rl_llm_vs_sem_pct") is not None \
                and comparacao["reducao_rl_llm_vs_sem_pct"] < 0:
            alertas.append(
                "rl_pior_que_sem_agente: política aprendida custa mais que não fazer nada — "
                "verifique convergência, pesos do reward ou se treino foi suficiente."
            )
        if eval_cmp.get("violacoes_pcc_total", 0) > 0:
            alertas.append(f"violacoes_pcc: {eval_cmp['violacoes_pcc_total']} horas com importação ≥ PCC.")
        if eval_cmp.get("violacoes_soc_total_h", 0) > 0:
            alertas.append(f"violacoes_soc: {eval_cmp['violacoes_soc_total_h']} horas com SOC < 15%.")

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
                "fazenda": state.dataset_meta["id_fazenda"],
                "n_dias": state.dataset_meta["n_dias"],
                "data_inicio": state.dataset_meta["data_inicio"],
                "data_fim": state.dataset_meta["data_fim"],
            },
            "agentes": info_ags,
            "cobertura_pct": cobertura,
            "n_estados_possiveis": N_ESTADOS_TOTAL,
            "soc_propagado_pct": round(float(state.iql.soc_propagado), 2),
            "treino": treino_resumo,
            "avaliacao_atual": eval_cmp,
            "comparacao_baselines": comparacao,
            "pesos_reward_modificados": pesos_modificados or None,
            "alertas": alertas,
        }, indent=2)
    except Exception as e:
        return _err(e)


@mcp.tool()
def describe_schema() -> str:
    """Esquema completo: estado, ações, restrições HARD, reward, tarifa, tracker_keys."""
    state = get_state()
    schema = {
        "arquitetura": "IQL (Independent Q-Learning) com 3 agentes cooperativos",
        "agentes": {
            "armazenamento": {"n_acoes": N_ACOES_ARMAZENAMENTO,
                              "valores": {0: "carregar", 1: "manter",
                                           2: "descarregar 25%", 3: "descarregar 50%",
                                           4: "descarregar 100%"}},
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
                "h":    "período energético → 7 (0-5 / 6-11 / 12-15 / 16-17 / 18-19 / 20 / 21-23h)",
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
            "bonus_carga_pico_geracao": CONFIG["bonus_carga_pico_geracao"],
            "bonus_excedente_exportado": CONFIG["bonus_excedente"],
            "bonus_soc_30_80": CONFIG["bonus_soc_ok"],
            "bonus_descarga_bateria_pico": CONFIG["bonus_descarga_pico"],
            "pen_descarga_fora_pico": -CONFIG["pen_descarga_fora_pico"],
            "pen_soc_final_por_pp": -CONFIG["pen_soc_final"],
            "pen_ciclos_por_kwh": -CONFIG["w_ciclos"],
            "pen_pico_demanda_por_kw": -CONFIG["w_pico_demanda"],
        },
        "tarifa_tou": {
            "min_rs_kwh": state.dataset_meta["tarifa_min_rs_kwh"],
            "max_rs_kwh": state.dataset_meta["tarifa_max_rs_kwh"],
            "horas_pico": state.dataset_meta["horas_pico"],
        },
        "tracker_keys_validos": ["iql_treino", "iql_eval", "rl_llm_mcp",
                                  "rl_padrao", "heuristico", "sem_agente", "iql_trace"],
        "info_step_campos": [
            "hora", "soc", "geracao_kw", "consumo_kw", "solar_kw", "eolico_kw",
            "rede_kwh", "excedente", "importacao", "exportacao", "custo_r",
            "tarifa", "reward", "a_arm", "a_cons", "a_ger", "bat_carga", "bat_descarga",
            "comando_bateria", "fluxo_bateria",
            "fracao_descarga_solicitada",
            "bonus_descarga_pico",
            "bonus_carga_pico_geracao",
            "pen_descarga_fora_pico",
            "pen_ciclos",
            "pen_pico_demanda",
            "pen_soc_final",
            "pico_importacao_dia",
            "motivo_descarga_bloqueada",
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
    initialize()
    if usar_stdio:
        mcp.run(transport="stdio")
    else:
        _log(f"Servidor MCP em http://{mcp.settings.host}:{mcp.settings.port}"
             f"{mcp.settings.streamable_http_path} (transporte streamable-http)")
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
