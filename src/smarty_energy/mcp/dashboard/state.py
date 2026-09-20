"""Helpers para manter o estado do dashboard em st.session_state.

Toda operação aqui é uma chamada de ferramenta MCP contra o servidor
`smarty_energy.mcp.server` (via `mcp_client`) — nenhuma métrica é calculada
localmente. O servidor MCP é quem detém o dataset, as Q-tables e o
tracker; o dashboard só armazena em cache o último payload JSON
retornado por cada tool, para renderização.
"""

from __future__ import annotations

import streamlit as st

from smarty_energy.mcp.dashboard.mcp_client import MCPServerError, call_tool

__all__ = [
    "ensure_state", "require_setup", "conectar_mcp", "sincronizar_status",
    "treinar", "treinar_rl_e_mcp", "avaliar", "comparar",
    "snapshot_policy", "carregar_politica_atual", "carregar_rl_padrao", "get_analysis_status",
    "save_experiment", "load_experiment", "list_experiments", "rename_experiment",
    "switch_dataset",
    "plan_dataset_splits", "get_split_experiment", "train_split_experiment", "evaluate_split_test",
    "health_report", "get_dataset_info", "get_qtables_info",
    "get_learning_curve", "get_td_error_series", "get_hourly_violations",
    "get_battery_dispatch_stats", "get_equipment_hourly", "get_equipment_stats", "export_all_data",
    "run_episode", "select_day", "identify_scenarios", "describe_schema",
    "MCPServerError",
]


def ensure_state() -> None:
    """Inicializa chaves esperadas no session_state, sem chamar o MCP."""
    ss = st.session_state
    ss.setdefault("mcp_conectado", False)
    ss.setdefault("meta", None)
    ss.setdefault("treinado", False)
    ss.setdefault("avaliado", False)
    ss.setdefault("comparado", False)
    ss.setdefault("rl_padrao_congelado", False)
    ss.setdefault("analysis_status", None)


def conectar_mcp() -> dict:
    """Verifica conectividade com o servidor MCP e busca metadados do dataset.

    O dataset já foi baixado e carregado dentro do processo do servidor
    no startup dele (`python server.py`) — aqui só confirmamos que o
    servidor está de pé e sincronizamos o dashboard com o que ele expõe.
    """
    ss = st.session_state
    meta = call_tool("get_dataset_info")
    sincronizar_status()
    ss.meta = meta
    ss.mcp_conectado = True
    return meta


def sincronizar_status() -> dict:
    """Sincroniza os indicadores da sessão com o estado real do servidor MCP."""
    ss = st.session_state
    status = get_analysis_status()
    ss.treinado = status["treinado"]
    ss.avaliado = status["avaliado"]
    ss.comparado = status["comparado"]
    ss.rl_padrao_congelado = status["rl_padrao_congelado"]
    ss.analysis_status = status
    return status


def require_setup() -> bool:
    """Mostra aviso se ainda não conectou ao MCP. Retorna True se ok."""
    ensure_state()
    if not st.session_state.mcp_conectado:
        st.info("Conecte ao servidor MCP usando o botão na barra lateral para começar "
                 "(o servidor precisa estar rodando: `python server.py`).")
        return False
    return True


# --- ações que envolvem treino/avaliação (encapsuladas para reuso entre páginas)

def treinar(n_episodios: int) -> dict:
    ss = st.session_state
    call_tool("configure_agents", n_episodios=n_episodios)
    sumario = call_tool("train_agents", n_episodios=n_episodios)
    ss.treinado = True
    ss.avaliado = False
    ss.comparado = False
    ss.rl_padrao_congelado = False
    ss.analysis_status = None
    ss.pop("export_payload", None)
    return sumario


def treinar_rl_e_mcp(n_episodios: int) -> dict:
    """Treina, num só passo, o RL padrão e o RL + LLM MCP (independentes)."""
    ss = st.session_state
    sumario = call_tool("train_rl_e_mcp", n_episodios=n_episodios)
    if "erro" not in sumario:
        ss.treinado = True
        ss.avaliado = False
        ss.comparado = False
        ss.pop("export_payload", None)
    return sumario


def avaliar(n_dias: int, propagar_soc: bool = True,
            continuar_do_treino: bool = False) -> dict:
    ss = st.session_state
    res = call_tool("evaluate_agents", n_dias=n_dias, propagar_soc=propagar_soc,
                    continuar_do_treino=continuar_do_treino)
    ss.avaliado = True
    return res


def comparar(n_dias: int, propagar_soc: bool = True,
             continuar_do_treino: bool = False) -> dict:
    """Avalia e compara as 4 estratégias num só passo (fonte única de medição)."""
    ss = st.session_state
    res = call_tool("compare_strategies", n_dias=n_dias, propagar_soc=propagar_soc,
                    continuar_do_treino=continuar_do_treino)
    ss.avaliado = True
    ss.comparado = True
    return res


def snapshot_policy(nome: str = "rl_padrao") -> dict:
    ss = st.session_state
    res = call_tool("snapshot_policy", nome=nome)
    ss.rl_padrao_congelado = True
    return res


# --- experimentos (modelos salvos: par RL padrão + RL + LLM MCP) ---

def save_experiment(label: str = "") -> dict:
    return call_tool("save_experiment", label=label)


def load_experiment(exp_id: str = "") -> dict:
    """Restaura um modelo salvo — estado volta a 'treinado' sem retreinar."""
    ss = st.session_state
    res = call_tool("load_experiment", exp_id=exp_id)
    if "erro" not in res:
        ss.treinado = True
        ss.avaliado = False
        ss.comparado = False
        ss.rl_padrao_congelado = True
        ss.pop("export_payload", None)
    return res


def list_experiments() -> dict:
    return call_tool("list_experiments")


def rename_experiment(exp_id: str, novo_label: str) -> dict:
    return call_tool("rename_experiment", exp_id=exp_id, novo_label=novo_label)


def switch_dataset(dataset_dir: str, id_fazenda: str = "", mes: int = 1) -> dict:
    """Troca a fazenda ativa do servidor — reset completo do estado de análise."""
    ss = st.session_state
    res = call_tool("switch_dataset", dataset_dir=dataset_dir,
                    id_fazenda=id_fazenda, mes=mes)
    if "erro" not in res:
        ss.meta = get_dataset_info()
        ss.treinado = False
        ss.avaliado = False
        ss.comparado = False
        ss.rl_padrao_congelado = False
        ss.pop("export_payload", None)
    return res


def plan_dataset_splits(metodos: list[str], **opcoes) -> dict:
    return call_tool("plan_dataset_splits", metodos=metodos, **opcoes)


def get_split_experiment(plano_id: str) -> dict:
    return call_tool("get_split_experiment", plano_id=plano_id)


def train_split_experiment(plano_id: str, divisao_id: str) -> dict:
    return call_tool("train_split_experiment", plano_id=plano_id, divisao_id=divisao_id)


def evaluate_split_test(plano_id: str, divisao_id: str, confirmar: bool = False) -> dict:
    return call_tool("evaluate_split_test", plano_id=plano_id,
                     divisao_id=divisao_id, confirmar=confirmar)


def carregar_politica_atual(run_id: str = "") -> dict:
    """Carrega um run salvo na política IQL viva usada pelo trace e avaliação."""
    ss = st.session_state
    res = call_tool("load_qtables", run_id=run_id)
    ss.treinado = "erro" not in res
    ss.avaliado = False
    ss.comparado = False
    ss.analysis_status = None
    return res


def carregar_rl_padrao(dir_path: str = "", run_id: str = "") -> dict:
    """Define o braço 'RL padrão' a partir de um run treinado (ex.: Smart_Energy)."""
    return call_tool("carregar_rl_padrao", dir_path=dir_path, run_id=run_id)


def get_analysis_status() -> dict:
    return call_tool("get_analysis_status")


# --- leitura de métricas/diagnóstico (todas via tool MCP) ------------------

def health_report() -> dict:
    return call_tool("health_report")


def get_dataset_info() -> dict:
    return call_tool("get_dataset_info")


def get_qtables_info() -> dict:
    return call_tool("get_qtables_info")


def get_learning_curve(janela_media_movel: int = 20) -> dict:
    return call_tool("get_learning_curve", janela_media_movel=janela_media_movel)


def get_td_error_series(agente: str) -> dict:
    return call_tool("get_td_error_series", agente=agente)


def get_hourly_violations(agente: str = "rl_llm_mcp") -> dict:
    return call_tool("get_hourly_violations", agente=agente)


def get_battery_dispatch_stats(agente: str = "rl_llm_mcp") -> dict:
    return call_tool("get_battery_dispatch_stats", agente=agente)


def get_equipment_hourly(agente: str = "rl_llm_mcp") -> dict:
    return call_tool("get_equipment_hourly", agente=agente)


def get_equipment_stats(agente: str = "rl_llm_mcp") -> dict:
    return call_tool("get_equipment_stats", agente=agente)


def export_all_data() -> dict:
    return call_tool("export_all_data")


def run_episode(mode: str = "eval", dia_idx: int | None = None,
                continuar_soc: bool = True, policy: str = "rl_llm_mcp") -> dict:
    return call_tool("run_episode", mode=mode, dia_idx=dia_idx,
                     continuar_soc=continuar_soc, policy=policy)


def select_day(dia_idx: int) -> dict:
    return call_tool("select_day", dia_idx=dia_idx)


def identify_scenarios() -> dict:
    return call_tool("identify_scenarios")


def describe_schema() -> dict:
    return call_tool("describe_schema")
