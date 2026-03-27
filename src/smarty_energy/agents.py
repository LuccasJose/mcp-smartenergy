"""
Agentes do sistema SmartEnergy MAS.

AgenteQL          — Q-Learning independente (IQL) com política epsilon-greedy.
AgentesHeuristicos — Baseline baseado em regras (sem aprendizado).
"""

import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np

from .config import CONFIG


class AgenteQL:
    """Agente de Q-Learning com política epsilon-greedy.

    Todos os agentes recebem o mesmo reward cooperativo do ambiente,
    alinhando o aprendizado individual ao objetivo global.
    """

    def __init__(self, n_acoes: int, nome: str, cfg: dict = CONFIG):
        self.n_acoes   = n_acoes
        self.nome      = nome
        self.epsilon   = cfg["epsilon_inicial"]
        self.alpha     = cfg["alpha"]
        self.gamma     = cfg["gamma"]
        self.eps_min   = cfg["epsilon_final"]
        self.eps_decay = cfg["epsilon_decay"]
        self.q_table   = defaultdict(lambda: np.zeros(n_acoes))
        self.n_updates = 0

    def agir(self, estado_disc: tuple, explorando: bool = True) -> int:
        """Seleciona uma ação via política epsilon-greedy."""
        if explorando and np.random.random() < self.epsilon:
            return np.random.randint(self.n_acoes)
        return int(np.argmax(self.q_table[estado_disc]))

    def aprender(self, s: tuple, a: int, r: float, s2: tuple, done: bool) -> None:
        """Atualização Q-Learning: Q[s][a] += α(r + γ·max(Q[s']) - Q[s][a])."""
        q_atual = self.q_table[s][a]
        q_alvo  = r if done else r + self.gamma * np.max(self.q_table[s2])
        self.q_table[s][a] += self.alpha * (q_alvo - q_atual)
        self.n_updates += 1

    def decair_epsilon(self) -> None:
        """Reduz epsilon multiplicativamente (decaimento exponencial)."""
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)

    @property
    def n_estados(self) -> int:
        """Número de estados distintos visitados."""
        return len(self.q_table)

    def save(self, path: str | Path) -> None:
        """Persiste a Q-table em disco via pickle."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"q_table": dict(self.q_table), "epsilon": self.epsilon,
                         "n_updates": self.n_updates, "nome": self.nome}, f)

    def load(self, path: str | Path) -> None:
        """Carrega uma Q-table salva anteriormente."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.q_table   = defaultdict(lambda: np.zeros(self.n_acoes), data["q_table"])
        self.epsilon   = data["epsilon"]
        self.n_updates = data["n_updates"]


class AgentesHeuristicos:
    """Baseline com regras fixas para comparação com o RL.

    Implementa o índice de estresse financeiro (0–100) e regras
    derivadas do documento SmartEnergy MAS v1.1.
    """

    def stress_financeiro(self, est: dict) -> float:
        """Índice de estresse financeiro (0–100)."""
        t_min = 0.681282
        t_max = 1.103868
        s_tar = (est["tarifa"] - t_min) / (t_max - t_min) * 70.0
        s_bat = 30.0 if est["soc"] < 20 else (10.0 if est["soc"] < 40 else 0.0)
        return min(100.0, s_tar + s_bat)

    def armazenamento(self, est: dict) -> int:
        """Regra: carrega com sol, descarrega no pico tarifário."""
        soc    = est["soc"]
        solar  = est["solar_kw"]
        tarifa = est["tarifa"]
        if soc > CONFIG["soc_max_pct"]:
            return 1                      # cheio → manter
        if soc < CONFIG["soc_min_pct"] + 2:
            return 1                      # crítico → não forçar descarga
        if tarifa > 0.9:
            return 2                      # pico tarifário → descarregar
        if solar > 10 and soc < 80:
            return 0                      # sol alto → carregar
        if solar > 3 and soc < 50:
            return 0
        return 1                          # default: manter

    def consumo(self, est: dict, stress: float) -> int:
        """Regra: corta cargas pelo nível de estresse financeiro."""
        if stress > 75:
            return 3                      # corta pivô + captação
        if stress > 50:
            return 2                      # corta só captação (maior carga)
        if stress > 25:
            return 1                      # corta só pivô
        return 0                          # sem corte

    def gerente(self, est: dict, stress: float) -> int:
        """Regra: define teto de consumo pelo nível de estresse."""
        if stress > 70:
            return 0                      # conservador (20 kW)
        if stress > 35:
            return 1                      # moderado    (30 kW)
        return 2                          # liberal     (40 kW)
