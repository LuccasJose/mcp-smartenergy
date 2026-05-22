"""
AgenteQL — Q-learning histérico (Hysteretic Q-learning).

Diferença em relação à versão monolítica anterior do MCP: agora cada
agente tem `n_acoes` parametrizável (3, 8 ou 3) e a orquestração dos
três agentes independentes (IQL) é feita por `IQLSystem`, espelhando
o projeto Smart_Energy.

Reward cooperativo: o env emite um único reward; os três agentes
recebem o mesmo valor e cada um atualiza apenas sua própria ação.
"""

import json
import pickle
import numpy as np
from collections import defaultdict
from pathlib import Path

from config import (
    CONFIG, N_ACOES_ARMAZENAMENTO, N_ACOES_CONSUMO, N_ACOES_GERENTE,
    N_ESTADOS_TOTAL,
)


class AgenteQL:
    """Q-learning histérico (alpha otimista, beta pessimista)."""

    def __init__(self, n_acoes: int, nome: str = "ql", cfg: dict = CONFIG):
        self.n_acoes  = n_acoes
        self.nome     = nome
        self.cfg      = cfg
        self.alpha    = cfg["alpha"]
        self.beta     = cfg.get("beta", 0.01)
        self.gamma    = cfg["gamma"]
        self.epsilon  = cfg["epsilon_inicial"]
        self.eps_min  = cfg["epsilon_final"]
        self.eps_decay = cfg["epsilon_decay"]

        self.q_table: dict[tuple, np.ndarray] = defaultdict(
            lambda: np.zeros(n_acoes, dtype=np.float64)
        )
        self.rng = np.random.default_rng()
        self.n_updates = 0

        # Métricas de convergência (Sprint 2 — aproveitamos a reescrita)
        self.td_errors: list[float] = []
        self.td_errors_max_len = 5000   # janela rolante para diagnóstico

    def agir(self, estado: tuple, explorando: bool = True) -> int:
        if explorando and self.rng.random() < self.epsilon:
            return int(self.rng.integers(self.n_acoes))
        return int(np.argmax(self.q_table[estado]))

    def aprender(self, s: tuple, a: int, r: float, s2: tuple, done: bool) -> None:
        q_atual = self.q_table[s][a]
        q_alvo  = r if done else r + self.gamma * float(np.max(self.q_table[s2]))
        td = q_alvo - q_atual
        lr = self.alpha if td >= 0 else self.beta
        self.q_table[s][a] += lr * td
        self.n_updates += 1
        self.td_errors.append(td)
        if len(self.td_errors) > self.td_errors_max_len:
            self.td_errors = self.td_errors[-self.td_errors_max_len:]

    def decair_epsilon(self) -> None:
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)

    @property
    def n_estados(self) -> int:
        return len(self.q_table)

    def td_error_recente(self, janela: int = 500) -> dict:
        if not self.td_errors:
            return {"janela": 0, "td_abs_medio": 0.0, "td_std": 0.0}
        amostra = self.td_errors[-janela:]
        return {
            "janela": len(amostra),
            "td_abs_medio": float(np.mean(np.abs(amostra))),
            "td_std": float(np.std(amostra)),
        }

    def get_info(self) -> dict:
        return {
            "nome": self.nome,
            "n_acoes": self.n_acoes,
            "n_estados_visitados": self.n_estados,
            "n_updates": self.n_updates,
            "epsilon": float(self.epsilon),
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
            "td_error_recente": self.td_error_recente(),
        }

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "nome": self.nome,
                "n_acoes": self.n_acoes,
                "q_table": dict(self.q_table),
                "epsilon": self.epsilon,
                "n_updates": self.n_updates,
            }, f)

    def load(self, path: str | Path) -> None:
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.n_acoes   = data.get("n_acoes", self.n_acoes)
        self.q_table   = defaultdict(lambda: np.zeros(self.n_acoes, dtype=np.float64), data["q_table"])
        self.epsilon   = data.get("epsilon", self.epsilon)
        self.n_updates = data.get("n_updates", 0)


class IQLSystem:
    """Orquestra os 3 agentes IQL (armazenamento, consumo, gerente)."""

    def __init__(self, cfg: dict = CONFIG):
        self.cfg = cfg
        self.agentes = {
            "armazenamento": AgenteQL(N_ACOES_ARMAZENAMENTO, "armazenamento", cfg),
            "consumo":       AgenteQL(N_ACOES_CONSUMO,       "consumo",       cfg),
            "gerente":       AgenteQL(N_ACOES_GERENTE,       "gerente",       cfg),
        }
        self.n_episodios = cfg["n_episodios"]
        self.soc_propagado = cfg["soc_inicial_pct"]   # SOC inicial do próximo episódio

    # ------------------------------------------------------------------ #
    # API uniforme                                                         #
    # ------------------------------------------------------------------ #

    def agir_todos(self, estado: tuple, explorando: bool = True) -> tuple[int, int, int]:
        return (
            self.agentes["armazenamento"].agir(estado, explorando),
            self.agentes["consumo"].agir(estado,       explorando),
            self.agentes["gerente"].agir(estado,       explorando),
        )

    def aprender_todos(self, s, acoes: tuple[int, int, int], r, s2, done):
        a_arm, a_cons, a_ger = acoes
        self.agentes["armazenamento"].aprender(s, a_arm,  r, s2, done)
        self.agentes["consumo"].aprender(      s, a_cons, r, s2, done)
        self.agentes["gerente"].aprender(      s, a_ger,  r, s2, done)

    def decair_epsilon_todos(self):
        for ag in self.agentes.values():
            ag.decair_epsilon()

    def reconfigurar(self, novos_params: dict):
        """Atualiza hiperparâmetros (sem destruir as Q-tables)."""
        for ag in self.agentes.values():
            for k, v in novos_params.items():
                if k == "alpha":
                    ag.alpha = v
                elif k == "beta":
                    ag.beta = v
                elif k == "gamma":
                    ag.gamma = v
                elif k == "epsilon_inicial":
                    ag.epsilon = v
                elif k == "epsilon_final":
                    ag.eps_min = v
                elif k == "epsilon_decay":
                    ag.eps_decay = v
        if "n_episodios" in novos_params:
            self.n_episodios = novos_params["n_episodios"]

    def reset_qtables(self):
        for ag in self.agentes.values():
            ag.q_table = defaultdict(lambda n=ag.n_acoes: np.zeros(n, dtype=np.float64))
            ag.n_updates = 0
            ag.td_errors = []
            ag.epsilon = ag.cfg["epsilon_inicial"]

    # ------------------------------------------------------------------ #
    # Treino IQL com SOC propagado entre dias                              #
    # ------------------------------------------------------------------ #

    def treinar(self, dias, tarifa_24h, env_cls, tracker=None) -> dict:
        """Loop IQL espelhando training.treinar do Smart_Energy.

        env_cls é a classe FazendaEnergyEnv passada por injeção (evita import circular).
        SOC inicial de cada episódio = SOC final do anterior, simulando continuidade real.
        """
        rewards_hist, custos_hist, eps_hist = [], [], []
        soc_proximo = self.cfg["soc_inicial_pct"]

        for ep in range(self.n_episodios):
            dados_dia = dias[ep % len(dias)]
            env = env_cls(dados_dia, tarifa_24h, self.cfg)
            est = env.reset(soc_inicial=soc_proximo)
            s   = env.discretizar(est)

            ep_reward = 0.0
            ep_custo  = 0.0

            for _ in range(24):
                acoes = self.agir_todos(s, explorando=True)
                prox, reward, done, info = env.step(*acoes)
                s2 = env.discretizar(prox)
                self.aprender_todos(s, acoes, reward, s2, done)
                s = s2
                ep_reward += reward
                ep_custo  += info["custo_r"]
                if tracker:
                    tracker.registrar_passo(info, agente="iql_treino")

            soc_proximo = env.soc
            self.decair_epsilon_todos()
            rewards_hist.append(ep_reward)
            custos_hist.append(ep_custo)
            eps_hist.append(self.agentes["armazenamento"].epsilon)

            if tracker:
                tracker.fechar_episodio(
                    agente="iql_treino",
                    reward_total=ep_reward,
                    custo_total=ep_custo,
                    epsilon=self.agentes["armazenamento"].epsilon,
                    cenario="REAL",   # cenário viria de classificação ex-post
                )

        self.soc_propagado = soc_proximo
        n = len(rewards_hist)
        janela = min(50, n)
        return {
            "episodios_treinados": n,
            "reward_ultimo_ep": float(rewards_hist[-1]) if n else 0.0,
            "reward_media_ultimos_50": float(np.mean(rewards_hist[-janela:])) if n else 0.0,
            "custo_medio_ultimos_50_rs": float(np.mean(custos_hist[-janela:])) if n else 0.0,
            "epsilon_final": float(eps_hist[-1]) if n else 0.0,
            "soc_propagado_final_pct": float(soc_proximo),
            "agentes": {n: ag.get_info() for n, ag in self.agentes.items()},
        }

    # ------------------------------------------------------------------ #
    # Avaliação greedy                                                     #
    # ------------------------------------------------------------------ #

    def avaliar(self, dias, tarifa_24h, env_cls, n_dias: int = 30,
                tracker=None, tracker_key: str = "iql_eval",
                propagar_soc: bool = True) -> dict:
        custos, redes, viols_soc, rewards = [], [], [], []
        soc_proximo = self.cfg["soc_inicial_pct"]

        for ep in range(n_dias):
            dados_dia = dias[ep % len(dias)]
            env = env_cls(dados_dia, tarifa_24h, self.cfg)
            est = env.reset(soc_inicial=soc_proximo)
            s   = env.discretizar(est)

            custo_dia = rede_dia = viols = reward_dia = 0.0
            for _ in range(24):
                acoes = self.agir_todos(s, explorando=False)
                prox, reward, done, info = env.step(*acoes)
                s2 = env.discretizar(prox)
                s = s2
                custo_dia += info["custo_r"]
                rede_dia  += info["rede_kwh"]
                reward_dia += info["reward"]
                if info["soc"] < self.cfg["soc_min_pct"]:
                    viols += 1
                if tracker:
                    tracker.registrar_passo(info, agente=tracker_key)

            if propagar_soc:
                soc_proximo = env.soc

            custos.append(custo_dia)
            redes.append(rede_dia)
            viols_soc.append(viols)
            rewards.append(reward_dia)

            if tracker:
                tracker.fechar_episodio(
                    agente=tracker_key,
                    reward_total=reward_dia,
                    custo_total=custo_dia,
                    epsilon=0.0,
                    cenario="REAL",
                )

        return {
            "n_dias": n_dias,
            "custo_medio_dia_rs": float(np.mean(custos)),
            "custo_std": float(np.std(custos)),
            "rede_media_dia_kwh": float(np.mean(redes)),
            "violacoes_soc_media_h_dia": float(np.mean(viols_soc)),
            "reward_medio_dia": float(np.mean(rewards)),
        }

    # ------------------------------------------------------------------ #
    # Persistência                                                         #
    # ------------------------------------------------------------------ #

    def save_all(self, dir_path: str | Path):
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        for nome, ag in self.agentes.items():
            ag.save(dir_path / f"qtable_{nome}.pkl")

    def load_all(self, dir_path: str | Path):
        dir_path = Path(dir_path)
        for nome, ag in self.agentes.items():
            p = dir_path / f"qtable_{nome}.pkl"
            if p.exists():
                ag.load(p)
            else:
                raise FileNotFoundError(f"Q-table não encontrada: {p}")
