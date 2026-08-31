"""Experimentos — snapshots pareados dos 2 braços RL do servidor MCP.

Um "experimento" congela em disco o par treinado pelo servidor:
    - braço vivo  'RL + LLM MCP' (Q-tables da política IQL)
    - braço fixo  'RL padrão'    (snapshot congelado de referência)
junto com os pesos do reward vigentes e metadados — o suficiente para
restaurar o estado "treinado e comparável" sem retreinar.

Layout em ``outputs/experimentos/<exp_id>/``:
    rl_llm_mcp/qtable_<agente>.pkl   (formato AgenteQL.save — 3 arquivos)
    rl_padrao_snapshot.pkl           (dict {agente: {estado: qvalues}})
    training_history.pkl             (hist do braço vivo; opcional)
    meta.json                        (label, pesos, encoding, física, custos)

O ``exp_id`` é um timestamp (ordenável); o ``label`` é livre e renomeável.
"""

from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path

from ..config import CONFIG, OUTPUT_DIR
from ..environment import STATE_ENCODING_VERSION
from ..runs import _PARAMS_FISICOS

EXP_DIR = OUTPUT_DIR / "experimentos"


def novo_exp_id() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def caminho(exp_id: str) -> Path:
    return EXP_DIR / exp_id


def _meta_path(exp_id: str) -> Path:
    return caminho(exp_id) / "meta.json"


def _ler_meta(exp_id: str) -> dict:
    with open(_meta_path(exp_id), encoding="utf-8") as f:
        return json.load(f)


def _escrever_meta(exp_id: str, meta: dict) -> None:
    with open(_meta_path(exp_id), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def salvar(
    agentes_vivos: dict,
    snapshot_rl_padrao: dict,
    *,
    label: str = "",
    hist: dict | None = None,
    pesos_reward: dict | None = None,
    fonte_dados: str | None = None,
    soc_propagado: float | None = None,
    rl_padrao_travado: bool = False,
    custos: dict | None = None,
) -> str:
    """Persiste o par de braços e devolve o exp_id.

    ``label`` vazio vira ``"<n_episodios>ep"`` (ex.: "50000ep") — o número de
    episódios sai do hist quando disponível.
    """
    exp_id = novo_exp_id()
    destino = caminho(exp_id)
    seq = 1
    while destino.exists():                 # colisão no mesmo segundo
        seq += 1
        destino = caminho(f"{exp_id}-{seq}")
    exp_id = destino.name
    (destino / "rl_llm_mcp").mkdir(parents=True, exist_ok=True)

    for nome, ag in agentes_vivos.items():
        ag.save(destino / "rl_llm_mcp" / f"qtable_{nome}.pkl")

    with open(destino / "rl_padrao_snapshot.pkl", "wb") as f:
        pickle.dump(snapshot_rl_padrao, f)

    if hist is not None:
        with open(destino / "training_history.pkl", "wb") as f:
            pickle.dump(hist, f)

    n_episodios = (hist or {}).get("n_episodios")
    pesos = pesos_reward or {}
    meta = {
        "exp_id": exp_id,
        "label": label or (f"{n_episodios}ep" if n_episodios else exp_id),
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "state_encoding_version": STATE_ENCODING_VERSION,
        "n_episodios": n_episodios,
        "best_ep": (hist or {}).get("best_ep"),
        "best_custo_med": (hist or {}).get("best_custo_med"),
        "fonte_dados": fonte_dados,
        "soc_propagado_pct": soc_propagado,
        "rl_padrao_travado": rl_padrao_travado,
        "pesos_reward": pesos,
        "fisica": {k: CONFIG[k] for k in _PARAMS_FISICOS if k in CONFIG},
        "estados_por_agente": {n: len(ag.q_table) for n, ag in agentes_vivos.items()},
        "custos": custos or {},
    }
    _escrever_meta(exp_id, meta)
    return exp_id


def carregar(exp_id: str, agentes_vivos: dict) -> tuple[dict, dict, dict | None]:
    """Restaura o experimento em ``agentes_vivos`` (in-place).

    Retorna ``(snapshot_rl_padrao, meta, hist)``. Levanta ``ValueError`` se o
    encoding de estado do experimento difere do atual — Q-tables de outra
    discretização produziriam política inválida sem nenhum aviso.
    """
    destino = caminho(exp_id)
    if not destino.exists():
        raise FileNotFoundError(f"Experimento '{exp_id}' não existe em {EXP_DIR}")

    meta = _ler_meta(exp_id)
    versao = meta.get("state_encoding_version")
    if versao != STATE_ENCODING_VERSION:
        raise ValueError(
            f"Experimento '{exp_id}' usa state_encoding_version={versao}, "
            f"mas o ambiente atual é v{STATE_ENCODING_VERSION} — "
            "as Q-tables não são compatíveis (retreine)."
        )

    for nome, ag in agentes_vivos.items():
        ag.load(destino / "rl_llm_mcp" / f"qtable_{nome}.pkl")

    with open(destino / "rl_padrao_snapshot.pkl", "rb") as f:
        snapshot = pickle.load(f)

    hist = None
    hist_path = destino / "training_history.pkl"
    if hist_path.exists():
        with open(hist_path, "rb") as f:
            hist = pickle.load(f)

    return snapshot, meta, hist


def avisos_fisica(meta: dict) -> list[str]:
    """Divergências entre a física salva no experimento e o CONFIG atual."""
    salva = meta.get("fisica", {})
    return [
        f"{k}: experimento={v} vs atual={CONFIG[k]}"
        for k, v in salva.items()
        if k in CONFIG and CONFIG[k] != v
    ]


def listar() -> list[dict]:
    """Metas de todos os experimentos, do mais recente para o mais antigo."""
    if not EXP_DIR.exists():
        return []
    metas = []
    for d in sorted(EXP_DIR.iterdir(), reverse=True):
        if (d / "meta.json").exists():
            try:
                metas.append(_ler_meta(d.name))
            except (json.JSONDecodeError, OSError):
                continue
    return metas


def mais_recente() -> str | None:
    metas = listar()
    return metas[0]["exp_id"] if metas else None


def renomear(exp_id: str, label: str) -> dict:
    """Troca o label (nome amigável) de um experimento salvo."""
    meta = _ler_meta(exp_id)
    meta["label"] = label
    _escrever_meta(exp_id, meta)
    return meta
