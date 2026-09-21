"""Orquestracao dos agentes IQL; delega treinamento ao motor compartilhado."""

from collections import defaultdict
from pathlib import Path

import numpy as np

from ..config import CONFIG
from .evaluation import avaliar_politica
from .q_learning import construir_agentes


class IQLSystem:
    """Orquestra os 3 agentes independentes (armazenamento, consumo, gerente).

    É a API de alto nível consumida pelo servidor MCP: agir/aprender em bloco,
    reconfigurar hiperparâmetros em runtime, treinar e avaliar. O treino delega
    a `training.treinar` — mesmo laço e selecao de checkpoint do pipeline offline.
    """

    def __init__(self, cfg: dict = CONFIG):
        # Cópia: `reconfigurar` escreve em self.cfg, e mutar o CONFIG global a
        # partir daí afetaria o pipeline inteiro. Quem precisa propagar (como o
        # servidor MCP, em configure_reward_weights) atualiza os dois na mão.
        self.cfg = dict(cfg)
        self.agentes = construir_agentes(self.cfg)
        self.n_episodios = cfg["n_episodios"]
        self.soc_propagado = cfg["soc_inicial_pct"]   # SOC inicial do próximo episódio
        # True quando alguém fixou epsilon_decay explicitamente — nesse caso
        # `treinar` respeita o valor em vez de reescalá-lo pelo horizonte.
        self.decay_manual = False
        # Histórico completo do último treino (formato de `training.treinar`),
        # usado para versionar o treino via `runs.salvar_run`.
        self.ultimo_hist: dict | None = None

    # -- API uniforme ---------------------------------------------------

    def agir_todos(self, estado: tuple, explorando: bool = True) -> tuple[int, int, int]:
        return (
            self.agentes["armazenamento"].agir(estado, explorando),
            self.agentes["consumo"].agir(estado,       explorando),
            self.agentes["gerente"].agir(estado,       explorando),
        )

    def aprender_todos(self, s, acoes: tuple[int, int, int], r, s2, done) -> None:
        a_arm, a_cons, a_ger = acoes
        self.agentes["armazenamento"].aprender(s, a_arm,  r, s2, done)
        self.agentes["consumo"].aprender(      s, a_cons, r, s2, done)
        self.agentes["gerente"].aprender(      s, a_ger,  r, s2, done)

    def decair_epsilon_todos(self) -> None:
        for ag in self.agentes.values():
            ag.decair_epsilon()

    def reconfigurar(self, novos_params: dict) -> None:
        """Atualiza hiperparâmetros dos 3 agentes sem destruir as Q-tables."""
        atributo = {
            "alpha": "alpha", "beta": "beta", "gamma": "gamma",
            "epsilon_inicial": "epsilon", "epsilon_final": "eps_min",
            "epsilon_decay": "eps_decay",
        }
        for ag in self.agentes.values():
            for k, v in novos_params.items():
                if k in atributo:
                    setattr(ag, atributo[k], v)
        self.cfg.update({k: v for k, v in novos_params.items() if k in self.cfg})
        if "n_episodios" in novos_params:
            self.n_episodios = novos_params["n_episodios"]
        if "epsilon_decay" in novos_params:
            self.decay_manual = True

    def reset_qtables(self) -> None:
        for ag in self.agentes.values():
            ag.q_table = defaultdict(lambda n=ag.n_acoes: np.zeros(n))
            ag.n_updates = 0
            ag.td_errors = []
            ag.epsilon = self.cfg["epsilon_inicial"]

    # -- Treino e avaliação ---------------------------------------------

    def treinar(self, dias, tarifa_24h, env_cls=None, tracker=None, log=None) -> dict:
        """Treina os 3 agentes por `self.n_episodios` e devolve o sumário.

        Delega a `training.treinar` (horizonte completo e restauracao do checkpoint),
        reescalando o decaimento de ε para o horizonte pedido — sem isso, um
        treino curto de servidor herdaria o decay calibrado para 100k episódios
        e os agentes ficariam aleatórios até o fim. Se alguém fixou
        `epsilon_decay` via `reconfigurar`, esse valor é respeitado.

        A selecao legada usa um dia a cada tres quando ha pelo menos seis dias.
        Esses dias tambem participam do treino: nao e um holdout independente.
        O protocolo com conjuntos separados pertence a `PlanoDivisoes`.
        """
        from ..config import ajustar_decay
        from ..training import treinar as treinar_loop

        if self.decay_manual:
            cfg = {**self.cfg, "n_episodios": self.n_episodios}
        else:
            cfg = ajustar_decay(self.cfg, self.n_episodios)
            for ag in self.agentes.values():
                ag.eps_decay = cfg["epsilon_decay"]
        dias_selecao = dias[::3] if len(dias) >= 6 else dias
        hist = treinar_loop(dias, tarifa_24h, self.agentes, cfg,
                            env_cls=env_cls, tracker=tracker, log=log,
                            dias_selecao=dias_selecao)

        self.ultimo_hist = hist
        self.soc_propagado = hist["soc_final_pct"]
        rewards, custos, eps = hist["rewards"], hist["custos"], hist["epsilons"]
        n = len(rewards)
        janela = min(50, n)
        return {
            "episodios_treinados": n,
            "reward_ultimo_ep": float(rewards[-1]) if n else 0.0,
            "reward_media_ultimos_50": float(np.mean(rewards[-janela:])) if n else 0.0,
            "custo_medio_ultimos_50_rs": float(np.mean(custos[-janela:])) if n else 0.0,
            "epsilon_final": float(eps[-1]) if n else 0.0,
            "soc_propagado_final_pct": float(self.soc_propagado),
            "best_ep": hist["best_ep"],
            "best_custo_med": hist["best_custo_med"],
            "duracao_s": hist["duracao_s"],
            "agentes": {nome: ag.get_info() for nome, ag in self.agentes.items()},
        }

    def avaliar(self, dias, tarifa_24h, env_cls=None, *, n_dias: int = 30,
                tracker=None, tracker_key: str = "iql_eval",
                propagar_soc: bool = True,
                soc_inicial: float | None = None) -> dict:
        """Avalia a política greedy dos 3 agentes (ver `avaliar_politica`)."""
        def escolher(env, est):
            return self.agir_todos(env.discretizar(est), explorando=False)

        return avaliar_politica(
            escolher, dias, tarifa_24h, cfg=self.cfg, env_cls=env_cls,
            n_dias=n_dias, tracker=tracker, tracker_key=tracker_key,
            propagar_soc=propagar_soc, soc_inicial=soc_inicial,
        )

    # -- Persistência ----------------------------------------------------

    def save_all(self, dir_path: str | Path) -> None:
        """Salva as 3 Q-tables em `dir_path/qtable_<nome>.pkl`.

        Mesmo layout de `runs.salvar_run`, então um diretório salvo aqui pode
        ser lido pelo pipeline offline e vice-versa.
        """
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        for nome, ag in self.agentes.items():
            ag.save(dir_path / f"qtable_{nome}.pkl")

    def load_all(self, dir_path: str | Path) -> None:
        dir_path = Path(dir_path)
        for nome, ag in self.agentes.items():
            p = dir_path / f"qtable_{nome}.pkl"
            if not p.exists():
                raise FileNotFoundError(f"Q-table não encontrada: {p}")
            ag.load(p)
