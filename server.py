"""
MCP Server – SmartEnergy Q-Learning
Expõe ferramentas para treinar, avaliar e monitorar o AgenteQL.
"""

import json
import sys
import os

# garante que imports relativos funcionem ao executar via mcp run
sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP

from environment.energy_env import EnergyEnvironment
from environment.scenarios import identificar_cenarios, stats_por_cenario
from agents.qlearning_agent import AgenteQL
from agents.baselines import AgenteHeuristico, SemAgente
from metrics.tracker import MetricsTracker
from config import DEFAULT_HYPERPARAMS

# ------------------------------------------------------------------ #
# Estado global do servidor                                            #
# ------------------------------------------------------------------ #

env = EnergyEnvironment()
agent = AgenteQL(**DEFAULT_HYPERPARAMS)
heuristico = AgenteHeuristico()
sem_agente = SemAgente()
tracker = MetricsTracker()

mcp = FastMCP("mcpsmartenergy")


# ------------------------------------------------------------------ #
# Ferramentas: configuração                                            #
# ------------------------------------------------------------------ #

@mcp.tool()
def configure_agent(
    n_episodios: int = DEFAULT_HYPERPARAMS["n_episodios"],
    alpha: float = DEFAULT_HYPERPARAMS["alpha"],
    gamma: float = DEFAULT_HYPERPARAMS["gamma"],
    beta: float = DEFAULT_HYPERPARAMS["beta"],
    epsilon_inicial: float = DEFAULT_HYPERPARAMS["epsilon_inicial"],
    epsilon_final: float = DEFAULT_HYPERPARAMS["epsilon_final"],
    epsilon_decay: float = DEFAULT_HYPERPARAMS["epsilon_decay"],
) -> str:
    """
    Reconfigura e reinicia o AgenteQL com novos hiperparâmetros.

    Hiperparâmetros:
    - n_episodios: episódios de treino
    - alpha: taxa de aprendizado otimista (atualizações positivas)
    - gamma: fator de desconto
    - beta: taxa de aprendizado pessimista — deve ser << alpha (hysteretic)
    - epsilon_inicial / epsilon_final / epsilon_decay: exploração ε-greedy
    """
    try:
        if not (0.0 < alpha <= 1.0):
            return json.dumps({"erro": "alpha deve estar em (0, 1]"}, indent=2)
        if not (0.0 < beta <= alpha):
            return json.dumps({"erro": "beta deve estar em (0, alpha] para hysteretic"}, indent=2)
        if not (0.0 < gamma < 1.0):
            return json.dumps({"erro": "gamma deve estar em (0, 1)"}, indent=2)
        global agent
        agent = AgenteQL(
            n_episodios=n_episodios,
            alpha=alpha,
            gamma=gamma,
            beta=beta,
            epsilon_inicial=epsilon_inicial,
            epsilon_final=epsilon_final,
            epsilon_decay=epsilon_decay,
        )
        return json.dumps({
            "status": "agente recriado",
            "hiperparametros": {
                "n_episodios": n_episodios,
                "alpha": alpha,
                "gamma": gamma,
                "beta": beta,
                "epsilon_inicial": epsilon_inicial,
                "epsilon_final": epsilon_final,
                "epsilon_decay": epsilon_decay,
            },
        }, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: treino                                                  #
# ------------------------------------------------------------------ #

@mcp.tool()
def train_agent(n_episodios: int = 0) -> str:
    """
    Treina o AgenteQL por N episódios (usa config do agente se n_episodios=0).
    Registra rewards_hist, custos_hist e epsilons no tracker.
    Retorna sumário do treino.
    """
    try:
        tracker.limpar("ql_treino")
        if n_episodios > 0:
            agent.n_episodios = n_episodios
        sumario = agent.train(env, tracker=tracker)
        return json.dumps(sumario, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: avaliação                                               #
# ------------------------------------------------------------------ #

@mcp.tool()
def evaluate_agent(n_dias: int = 30) -> str:
    """
    Avalia a política aprendida (greedy, sem exploração) por n_dias.
    Retorna métricas mensais: custo médio, rede, violações SOC, reward.
    """
    try:
        tracker.limpar("ql_eval")
        resultado = agent.evaluate(env, n_dias=n_dias, tracker=tracker)
        return json.dumps(resultado, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


@mcp.tool()
def compare_strategies(n_dias: int = 30) -> str:
    """
    Compara RL (AgenteQL) vs Heurístico vs Sem Agente em n_dias.
    Cada agente usa ambiente independente com seed=42 — mesma sequência de dias.
    Retorna custo médio, rede média, violações SOC e reward para cada estratégia.
    """
    try:
        # Cada agente recebe um env separado com a mesma seed para comparação justa
        resultados = {
            "RL (AgenteQL)": agent.evaluate(EnergyEnvironment(seed=42), n_dias=n_dias),
            "Heuristico": heuristico.evaluate(EnergyEnvironment(seed=42), n_dias=n_dias),
            "SemAgente": sem_agente.evaluate(EnergyEnvironment(seed=42), n_dias=n_dias),
        }

        custo_rl = resultados["RL (AgenteQL)"]["custo_medio_dia_rs"]
        custo_sem = resultados["SemAgente"]["custo_medio_dia_rs"]
        if custo_sem > 0:
            reducao_pct = (custo_sem - custo_rl) / custo_sem * 100
            resultados["reducao_custo_rl_vs_sem_agente_pct"] = round(reducao_pct, 2)

        return json.dumps(resultados, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: métricas de treino                                      #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_training_metrics() -> str:
    """
    Retorna métricas completas do último treino:
    rewards_hist, custos_hist, epsilons, médias e convergência.
    """
    metricas = tracker.get_training_metrics("ql_treino")
    qtable = agent.get_qtable_info()
    return json.dumps({"treino": metricas, "qtable": qtable}, indent=2)


@mcp.tool()
def get_qtable_info() -> str:
    """
    Retorna estatísticas da Q-table:
    - n_estados: estados distintos visitados
    - n_updates: total de atualizações Q-learning aplicadas
    - epsilon: taxa de exploração atual
    - hiperparâmetros configurados
    """
    return json.dumps(agent.get_qtable_info(), indent=2)


@mcp.tool()
def get_learning_curve(janela_media_movel: int = 20) -> str:
    """
    Retorna dados para a curva de aprendizado:
    reward e custo por episódio com média móvel.
    Útil para visualizar convergência do agente.
    """
    curva = tracker.get_learning_curve("ql_treino", janela=janela_media_movel)
    return json.dumps(curva, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: avaliação detalhada                                     #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_eval_metrics() -> str:
    """
    Retorna métricas detalhadas da última avaliação:
    custo, rede, violações SOC/PCC, kWh cortado, reward.
    """
    metricas = tracker.get_eval_metrics("ql_eval")
    return json.dumps(metricas, indent=2)


@mcp.tool()
def get_peak_offpeak_stats() -> str:
    """
    Retorna consumo de pivô, bomba e secador separado por
    período de pico e fora de pico (kWh e R$).
    """
    stats = tracker.get_peak_offpeak_stats("ql_eval")
    return json.dumps(stats, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: cenários                                                #
# ------------------------------------------------------------------ #

@mcp.tool()
def identify_scenario() -> str:
    """
    Identifica o cenário do último dia simulado:
    NUBLADO / ENSOLARADO / ALTO CONSUMO / EQUILIBRADO.
    """
    estado = env.get_full_state()
    return json.dumps({
        "cenario": estado["cenario_dia"],
        "solar_media_kw": round(float(env.solar_media_dia), 2),
        "consumo_medio_kw": round(float(env.consumo_medio_dia), 2),
    }, indent=2)


@mcp.tool()
def get_stats_por_cenario() -> str:
    """
    Retorna reward médio e custo médio por cenário
    (NUBLADO, ENSOLARADO, ALTO CONSUMO, EQUILIBRADO).
    """
    stats = tracker.get_stats_por_cenario("ql_eval")
    return json.dumps(stats, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: episódio manual                                         #
# ------------------------------------------------------------------ #

@mcp.tool()
def run_episode(mode: str = "eval") -> str:
    """
    Executa um episódio completo (24h) e retorna o trace hora-a-hora.

    mode: "train" (com exploração) | "eval" (política greedy)

    O trace inclui todos os campos de estado físico, energético,
    financeiro, ações e violações para cada hora do dia.
    """
    agente_key = "ql_trace"
    tracker.limpar(agente_key)

    obs = env.reset()
    state = agent.discretize(obs)
    done = False
    explore = mode == "train"
    reward_total = 0.0
    custo_total = 0.0

    while not done:
        action_id = agent.choose_action(state, explore=explore)
        a_arm, a_cons, a_ger = agent.decode_action(action_id)
        next_obs, reward, done, info = env.step(a_arm, a_cons, a_ger)

        if explore:
            next_state = agent.discretize(next_obs)
            agent.update(state, action_id, reward, next_state, done)
            state = next_state
        else:
            state = agent.discretize(next_obs)

        tracker.registrar_passo(info, agente=agente_key)
        reward_total += reward
        custo_total += info["custo_r"]

    trace = tracker.get_trace_ultimo_episodio(agente_key)
    return json.dumps({
        "mode": mode,
        "reward_total": round(reward_total, 4),
        "custo_total_rs": round(custo_total, 4),
        "cenario": getattr(env, "cenario_dia", "EQUILIBRADO"),
        "trace": trace,
    }, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: estado do ambiente                                      #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_current_state() -> str:
    """
    Retorna o estado atual do ambiente (hora, SOC, tarifas, geração prevista).
    """
    return json.dumps(env.get_full_state(), indent=2)


@mcp.tool()
def reset_environment(reset_agent: bool = False) -> str:
    """
    Reinicia o ambiente para um novo dia.
    Se reset_agent=True, apaga a Q-table e o histórico do agente.
    """
    env.reset()
    if reset_agent:
        global agent
        params = {
            "n_episodios": agent.n_episodios,
            "alpha": agent.alpha,
            "gamma": agent.gamma,
            "beta": agent.beta,
            "epsilon_inicial": agent.epsilon_inicial,
            "epsilon_final": agent.epsilon_final,
            "epsilon_decay": agent.epsilon_decay,
        }
        agent = AgenteQL(**params)
        tracker.limpar()

    return json.dumps({
        "status": "ambiente reiniciado",
        "agente_reiniciado": reset_agent,
        "estado": env.get_full_state(),
    }, indent=2)


# ------------------------------------------------------------------ #
# Ferramentas: integração com agente externo                           #
# ------------------------------------------------------------------ #

@mcp.tool()
def get_observation() -> str:
    """
    Retorna a observação atual do ambiente junto com o estado discretizado.
    Use antes de step_environment para que um agente externo consulte sua Q-table.

    Campos retornados:
    - obs: dicionário de observação (hora, soc, geracao_kw, ...)
    - state_discrete: tupla (hora, soc_b, pico, ger_b, cons_b, bomba_b)
    - state_index: representação string da tupla para lookup em JSON
    """
    try:
        obs = env._get_obs()
        state = agent.discretize(obs)
        return json.dumps({
            "obs": {k: (bool(v) if isinstance(v, bool) else v) for k, v in obs.items()},
            "state_discrete": list(state),
            "state_index": str(state),
        }, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


@mcp.tool()
def step_environment(a_arm: int, a_cons: int, a_ger: int) -> str:
    """
    Executa um único passo no ambiente com as ações fornecidas.
    Retorna (obs, reward, done, info) — interface primária para agente externo.

    Ações:
    - a_arm: 0=carregar, 1=manter, 2=descarregar
    - a_cons: bitmask 3 bits — bit0=cortar_pivô, bit1=cortar_bomba, bit2=cortar_secador
    - a_ger: 0=conservador (teto 20kW), 1=moderado (35kW), 2=liberal (55kW)
    """
    try:
        if a_arm not in (0, 1, 2):
            return json.dumps({"erro": f"a_arm inválido: {a_arm} (esperado 0-2)"}, indent=2)
        if not (0 <= a_cons <= 7):
            return json.dumps({"erro": f"a_cons inválido: {a_cons} (esperado 0-7)"}, indent=2)
        if a_ger not in (0, 1, 2):
            return json.dumps({"erro": f"a_ger inválido: {a_ger} (esperado 0-2)"}, indent=2)

        next_obs, reward, done, info = env.step(a_arm, a_cons, a_ger)
        next_state = agent.discretize(next_obs)

        return json.dumps({
            "reward": round(reward, 6),
            "done": done,
            "next_state_discrete": list(next_state),
            "next_state_index": str(next_state),
            "obs": {k: (bool(v) if isinstance(v, bool) else v) for k, v in next_obs.items()},
            "info": {k: (bool(v) if isinstance(v, bool) else round(v, 6) if isinstance(v, float) else v)
                     for k, v in info.items()},
        }, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


@mcp.tool()
def get_action(explore: bool = False) -> str:
    """
    Retorna a ação escolhida pelo AgenteQL para o estado atual do ambiente.
    explore=False usa política greedy; explore=True usa ε-greedy.
    Retorna action_id, (a_arm, a_cons, a_ger) e Q-values das top-5 ações.
    """
    try:
        obs = env._get_obs()
        state = agent.discretize(obs)
        action_id = agent.choose_action(state, explore=explore)
        a_arm, a_cons, a_ger = agent.decode_action(action_id)
        q_vals = agent.q_table[state]
        top5 = sorted(enumerate(q_vals.tolist()), key=lambda x: -x[1])[:5]
        return json.dumps({
            "action_id": action_id,
            "a_arm": a_arm,
            "a_cons": a_cons,
            "a_ger": a_ger,
            "q_value": round(float(q_vals[action_id]), 6),
            "explore_mode": explore,
            "epsilon": round(agent.epsilon, 4),
            "top5_actions": [{"action_id": aid, "q": round(q, 6)} for aid, q in top5],
        }, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


@mcp.tool()
def save_qtable(filepath: str = "qtable.json") -> str:
    """
    Salva a Q-table treinada em um arquivo JSON para persistência ou transferência.
    O arquivo pode ser recarregado com load_qtable.
    """
    try:
        agent.save_qtable(filepath)
        return json.dumps({
            "status": "Q-table salva",
            "filepath": filepath,
            "n_estados": len(agent.q_table),
            "n_updates": agent.n_updates,
        }, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


@mcp.tool()
def load_qtable(filepath: str = "qtable.json") -> str:
    """
    Carrega uma Q-table previamente salva com save_qtable.
    Restaura os Q-values e epsilon do agente.
    """
    try:
        agent.load_qtable(filepath)
        return json.dumps({
            "status": "Q-table carregada",
            "filepath": filepath,
            "n_estados": len(agent.q_table),
            "n_updates": agent.n_updates,
            "epsilon": round(agent.epsilon, 4),
        }, indent=2)
    except FileNotFoundError:
        return json.dumps({"erro": f"Arquivo não encontrado: {filepath}"}, indent=2)
    except Exception as e:
        return json.dumps({"erro": str(e)}, indent=2)


# ------------------------------------------------------------------ #
# Entrada                                                              #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    mcp.run()
