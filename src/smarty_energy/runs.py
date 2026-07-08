"""Versionamento de runs de treinamento.

Cada treino é persistido em ``outputs/runs/<run_id>/`` contendo:
    - qtable_<agente>.pkl   (uma por agente)
    - training_history.pkl  (rewards/custos/epsilons + metadados do treino)
    - meta.json             (resumo legível: data, nº episódios, custo, fonte)

O arquivo ``outputs/runs/latest.txt`` aponta para o run mais recente, usado
como padrão pelo ``--replot`` e pelos dashboards. Runs antigos ficam
disponíveis para reabrir/visualizar sem retreinar.
"""

from __future__ import annotations

import json
import pickle
import shutil
from datetime import datetime
from pathlib import Path

from .config import OUTPUT_DIR

RUNS_DIR = OUTPUT_DIR / "runs"
_LATEST = RUNS_DIR / "latest.txt"
_MODELS_LEGADO = OUTPUT_DIR / "models"


# ──────────────────────────────────────────────────────────────
# Identificação e caminhos
# ──────────────────────────────────────────────────────────────

def novo_run_id() -> str:
    """Gera um run_id por timestamp (ordenável lexicograficamente)."""
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def caminho_run(run_id: str) -> Path:
    return RUNS_DIR / run_id


# ──────────────────────────────────────────────────────────────
# Persistência
# ──────────────────────────────────────────────────────────────

def salvar_run(
    agentes: dict,
    hist: dict,
    *,
    run_id: str | None = None,
    fonte_dados: str | None = None,
) -> str:
    """Persiste um treino completo em ``outputs/runs/<run_id>/``.

    Args:
        agentes     : dict {chave: AgenteQL} já treinados.
        hist        : dict de histórico (rewards/custos/epsilons/...).
        run_id      : identificador; se None, gera por timestamp.
        fonte_dados : rótulo da base usada (ex. nome do .xlsx).

    Returns:
        O run_id efetivamente usado.
    """
    run_id = run_id or novo_run_id()
    destino = caminho_run(run_id)
    destino.mkdir(parents=True, exist_ok=True)

    for ag in agentes.values():
        ag.save(destino / f"qtable_{ag.nome.lower()}.pkl")

    with open(destino / "training_history.pkl", "wb") as f:
        pickle.dump(hist, f)

    meta = {
        "run_id"        : run_id,
        "criado_em"     : datetime.now().isoformat(timespec="seconds"),
        "n_episodios"   : hist.get("n_episodios"),
        "best_ep"       : hist.get("best_ep"),
        "best_custo_med": hist.get("best_custo_med"),
        "custo_final"   : hist.get("custo_final"),
        "reward_final"  : hist.get("reward_final"),
        "duracao_s"     : hist.get("duracao_s"),
        "hiperparametros": hist.get("hiperparametros", {}),
        "config_completo": hist.get("config_completo", {}),
        "fonte_dados"   : fonte_dados,
        "label"         : "",       # rótulo manual (editável pelo dashboard)
        "favorito"      : False,
    }
    _escrever_meta(run_id, meta)
    definir_latest(run_id)
    return run_id


def carregar_run(run_id: str, agentes: dict) -> dict:
    """Carrega as Q-tables do run em ``agentes`` e devolve o histórico.

    Os agentes devem ter sido instanciados com o mesmo nº de ações do treino.
    """
    origem = caminho_run(run_id)
    if not origem.exists():
        raise FileNotFoundError(f"Run '{run_id}' não encontrado em {RUNS_DIR}")
    for ag in agentes.values():
        ag.load(origem / f"qtable_{ag.nome.lower()}.pkl")
    with open(origem / "training_history.pkl", "rb") as f:
        return pickle.load(f)


def ler_historico(run_id: str) -> dict:
    """Carrega apenas o training_history.pkl do run (sem instanciar agentes).

    Útil para comparar curvas de aprendizado sem o custo de recarregar
    Q-tables e rodar o RL.
    """
    f = caminho_run(run_id) / "training_history.pkl"
    if not f.exists():
        raise FileNotFoundError(f"Histórico do run '{run_id}' não encontrado")
    with open(f, "rb") as fp:
        return pickle.load(fp)


def resultados_rl(run_id: str, dias, tarifa, cfg=None) -> tuple[list, dict]:
    """Carrega um run e roda o RL em todos os dias.

    Retorna ``(res_r, hist)`` onde ``res_r`` é a avaliação por dia (mesmo
    formato de ``evaluation.rodar_rl``) e ``hist`` é o histórico de treino.
    Imports tardios evitam ciclo de importação com agents/evaluation.
    """
    from .agents import construir_agentes
    from .config import CONFIG
    from .evaluation import rodar_rl

    agentes = construir_agentes(cfg or CONFIG)
    hist = carregar_run(run_id, agentes)
    res_r = [rodar_rl(d, tarifa, agentes) for d in dias]
    return res_r, hist


# ──────────────────────────────────────────────────────────────
# Descoberta / listagem
# ──────────────────────────────────────────────────────────────

def listar_run_ids() -> list[str]:
    """Run_ids existentes, do mais recente para o mais antigo."""
    if not RUNS_DIR.exists():
        return []
    ids = [
        p.name for p in RUNS_DIR.iterdir()
        if p.is_dir() and (p / "training_history.pkl").exists()
    ]
    return sorted(ids, reverse=True)


def listar_runs() -> list[dict]:
    """Runs disponíveis com metadados e rótulo legível (mais recente 1º)."""
    runs = []
    for rid in listar_run_ids():
        meta = ler_meta(rid)
        runs.append({"run_id": rid, "label": _rotulo(rid, meta), "meta": meta})
    return runs


def ler_meta(run_id: str) -> dict:
    f = caminho_run(run_id) / "meta.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def run_mais_recente() -> str | None:
    """Run padrão: o de ``latest.txt`` se válido, senão o mais novo por id."""
    if _LATEST.exists():
        rid = _LATEST.read_text(encoding="utf-8").strip()
        if rid and caminho_run(rid).exists():
            return rid
    ids = listar_run_ids()
    return ids[0] if ids else None


def definir_latest(run_id: str) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    _LATEST.write_text(run_id, encoding="utf-8")


# ──────────────────────────────────────────────────────────────
# Migração do layout antigo (outputs/models/)
# ──────────────────────────────────────────────────────────────

def migrar_legado() -> str | None:
    """Importa o antigo ``outputs/models/`` como um run, se ainda não houver runs.

    Returns:
        O run_id criado, ou None se não havia nada a migrar.
    """
    hist_antigo = _MODELS_LEGADO / "training_history.pkl"
    if not hist_antigo.exists() or listar_run_ids():
        return None

    # Usa a data de modificação do histórico como timestamp do run legado.
    ts = datetime.fromtimestamp(hist_antigo.stat().st_mtime)
    run_id = ts.strftime("%Y-%m-%d_%H%M%S") + "_legado"
    destino = caminho_run(run_id)
    destino.mkdir(parents=True, exist_ok=True)

    for arq in _MODELS_LEGADO.glob("*.pkl"):
        shutil.copy2(arq, destino / arq.name)

    try:
        with open(hist_antigo, "rb") as f:
            hist = pickle.load(f)
    except (pickle.PickleError, EOFError):
        hist = {}
    _escrever_meta(run_id, {
        "run_id"        : run_id,
        "criado_em"     : ts.isoformat(timespec="seconds"),
        "n_episodios"   : hist.get("n_episodios"),
        "best_ep"       : hist.get("best_ep"),
        "best_custo_med": hist.get("best_custo_med"),
        "custo_final"   : hist.get("custo_final"),
        "reward_final"  : hist.get("reward_final"),
        "duracao_s"     : hist.get("duracao_s"),
        "hiperparametros": hist.get("hiperparametros", {}),
        "config_completo": hist.get("config_completo", {}),
        "fonte_dados"   : "outputs/models (legado)",
        "label"         : "legado",
        "favorito"      : False,
    })
    definir_latest(run_id)
    return run_id


# ──────────────────────────────────────────────────────────────
# Gestão de runs (editar metadados / apagar)
# ──────────────────────────────────────────────────────────────

def atualizar_meta(run_id: str, **campos) -> dict:
    """Mescla `campos` no meta.json do run e devolve o meta atualizado."""
    meta = ler_meta(run_id)
    meta.update(campos)
    _escrever_meta(run_id, meta)
    return meta


def definir_label(run_id: str, label: str) -> dict:
    """Define o rótulo manual (string livre) de um run."""
    return atualizar_meta(run_id, label=(label or "").strip())


def definir_favorito(run_id: str, valor: bool) -> dict:
    return atualizar_meta(run_id, favorito=bool(valor))


def alternar_favorito(run_id: str) -> dict:
    """Inverte o status de favorito do run."""
    return definir_favorito(run_id, not ler_meta(run_id).get("favorito", False))


def deletar_run(run_id: str) -> str | None:
    """Remove um run do disco. Se era o `latest`, reaponta para o mais recente.

    Returns:
        O novo run padrão após a remoção, ou None se não sobrou nenhum.
    """
    destino = caminho_run(run_id)
    if destino.exists():
        shutil.rmtree(destino)

    era_latest = (
        _LATEST.exists()
        and _LATEST.read_text(encoding="utf-8").strip() == run_id
    )
    restantes = listar_run_ids()
    if era_latest:
        if restantes:
            definir_latest(restantes[0])
        else:
            _LATEST.unlink(missing_ok=True)
    return restantes[0] if restantes else None


# ──────────────────────────────────────────────────────────────
# Internos
# ──────────────────────────────────────────────────────────────

def _escrever_meta(run_id: str, meta: dict) -> None:
    f = caminho_run(run_id) / "meta.json"
    f.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _rotulo(run_id: str, meta: dict) -> str:
    estrela = "⭐ " if meta.get("favorito") else ""
    label = (meta.get("label") or "").strip()
    nome = f"{label} · {run_id}" if label else run_id

    partes = []
    n = meta.get("n_episodios")
    if n:
        partes.append(f"{n:,} ep".replace(",", "."))
    custo = meta.get("custo_final")
    if not isinstance(custo, (int, float)):
        custo = meta.get("best_custo_med")
    if isinstance(custo, (int, float)):
        partes.append(f"R${custo:.2f}")
    return estrela + nome + (f"  ({' · '.join(partes)})" if partes else "")
