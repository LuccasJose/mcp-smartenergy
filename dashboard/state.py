"""Helpers para manter o estado do dashboard em st.session_state.

Importa direto do projeto MCP (sem passar pelo transporte MCP) para
simplicidade de debug. Cada pagina pode chamar `require_setup()` para
garantir que o dataset/iql/env estao prontos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Garante que a raiz do projeto esta no path (dashboard/ -> raiz)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import CONFIG, N_ESTADOS_TOTAL
from environment.data_loader import carregar_dados
from environment.energy_env import FazendaEnergyEnv
from environment.scenarios import identificar_cenarios, classificar_dia
from agents.qlearning_agent import IQLSystem
from agents.baselines import AgentesHeuristicos, SemAgente
from metrics.tracker import MetricsTracker


# Reexporta nomes uteis (paginas podem fazer `from dashboard.state import ...`)
__all__ = [
    "ensure_state", "require_setup", "setup_dataset",
    "treinar", "avaliar", "comparar",
    "CONFIG", "N_ESTADOS_TOTAL",
    "FazendaEnergyEnv", "identificar_cenarios", "classificar_dia",
]


def ensure_state() -> None:
    """Inicializa chaves esperadas no session_state, sem disparar download."""
    ss = st.session_state
    ss.setdefault("dataset_carregado", False)
    ss.setdefault("dias", None)
    ss.setdefault("tarifa_24h", None)
    ss.setdefault("meta", None)
    ss.setdefault("iql", None)
    ss.setdefault("heuristico", None)
    ss.setdefault("sem_agente", None)
    ss.setdefault("tracker", None)
    ss.setdefault("treinado", False)
    ss.setdefault("avaliado", False)
    ss.setdefault("comparado", False)


def setup_dataset() -> None:
    """Baixa o dataset e instancia IQL/baselines/tracker.

    Disparado por botao na sidebar. Demora ~1s (download xlsx).
    """
    ss = st.session_state
    with st.spinner("Baixando dataset do Google Sheets..."):
        dias, tarifa, meta = carregar_dados()
    ss.dias = dias
    ss.tarifa_24h = tarifa
    ss.meta = meta
    ss.iql = IQLSystem(CONFIG)
    ss.heuristico = AgentesHeuristicos(CONFIG)
    ss.sem_agente = SemAgente(CONFIG)
    ss.tracker = MetricsTracker()
    ss.dataset_carregado = True
    ss.treinado = False
    ss.avaliado = False
    ss.comparado = False


def require_setup() -> bool:
    """Mostra aviso se dataset nao carregado. Retorna True se ok."""
    ensure_state()
    if not st.session_state.dataset_carregado:
        st.info("Carregue o dataset na sidebar para comecar.")
        return False
    return True


# --- acoes que envolvem treino/aval (encapsuladas para reuso entre paginas)

def treinar(n_episodios: int) -> dict:
    ss = st.session_state
    ss.iql.n_episodios = n_episodios
    ss.tracker.limpar("iql_treino")
    sumario = ss.iql.treinar(ss.dias, ss.tarifa_24h, FazendaEnergyEnv,
                              tracker=ss.tracker)
    ss.treinado = True
    return sumario


def avaliar(n_dias: int, propagar_soc: bool = True) -> dict:
    ss = st.session_state
    ss.tracker.limpar("iql_eval")
    res = ss.iql.avaliar(ss.dias, ss.tarifa_24h, FazendaEnergyEnv,
                          n_dias=n_dias, tracker=ss.tracker,
                          propagar_soc=propagar_soc)
    ss.avaliado = True
    return res


def comparar(n_dias: int, propagar_soc: bool = True) -> dict:
    ss = st.session_state
    for k in ("iql_eval", "iql_eval_cmp", "heuristico", "sem_agente"):
        ss.tracker.limpar(k)

    res_iql = ss.iql.avaliar(ss.dias, ss.tarifa_24h, FazendaEnergyEnv,
                              n_dias=n_dias, tracker=ss.tracker,
                              propagar_soc=propagar_soc)
    ss.tracker.passos["iql_eval_cmp"] = ss.tracker.passos.pop("iql_eval", [])
    ss.tracker.episodios["iql_eval_cmp"] = ss.tracker.episodios.pop("iql_eval", [])

    res_heur = ss.heuristico.avaliar(ss.dias, ss.tarifa_24h, FazendaEnergyEnv,
                                       n_dias=n_dias, tracker=ss.tracker,
                                       tracker_key="heuristico",
                                       propagar_soc=propagar_soc)
    res_sem = ss.sem_agente.avaliar(ss.dias, ss.tarifa_24h, FazendaEnergyEnv,
                                      n_dias=n_dias, tracker=ss.tracker,
                                      tracker_key="sem_agente",
                                      propagar_soc=propagar_soc)
    ss.comparado = True
    return {"IQL": res_iql, "Heuristico": res_heur, "SemAgente": res_sem}
