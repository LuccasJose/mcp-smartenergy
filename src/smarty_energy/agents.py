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
        self.beta      = cfg.get("beta", 0.01)  # taxa de aprendizado pessimista (Hysteretic)
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
        td_error = q_alvo - q_atual
        lr = self.alpha if td_error >= 0 else self.beta  # Hysteretic: otimista sobe rápido, pessimista desce devagar
        self.q_table[s][a] += lr * td_error
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


class AgenteFinanceiro:
    """Implementa a lógica de monitoramento de custos e créditos solares.

    Traduz o cenário econômico em um 'Índice de Estresse Financeiro' (0-100).
    """

    def __init__(self, cfg: dict = CONFIG):
        self.cfg = cfg
        self.saldo_creditos = cfg["credito_inicial_kwh"]

    def calcular_estresse(self, tarifa: float, consumo_atual: float) -> float:
        """Calcula o estresse financeiro baseado na tarifa e saldo de créditos."""
        # Baseline de estresse pela tarifa
        limiar = self.cfg["tarifa_estresse_limiar"]
        stress_tarifa = 70.0 if tarifa >= limiar else (tarifa / limiar) * 50.0

        # Penalidade por baixo saldo de créditos
        pen_credito = 30.0 if self.saldo_creditos < 20 else 0.0

        # Agrava se consumo está alto no pico
        agravante = 10.0 if (tarifa >= limiar and consumo_atual > 25.0) else 0.0

        return min(100.0, stress_tarifa + pen_credito + agravante)

    def atualizar_saldo(self, rede_kwh: float, excedente_kwh: float) -> None:
        """Atualiza o saldo de créditos (simplificado: 1 para 1)."""
        # Em um cenário real, haveria taxas de disponibilidade e impostos (TUSD/TE)
        self.saldo_creditos += excedente_kwh
        self.saldo_creditos -= rede_kwh
        self.saldo_creditos = max(0.0, self.saldo_creditos)


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
        """Regra: corta cargas pelo nível de estresse financeiro.
        
        Mapeamento 0-7:
        bit 0: pivo, bit 1: bomba, bit 2: secador
        """
        if stress > 85:
            return 7                      # corta tudo (4+2+1)
        if stress > 70:
            return 3                      # corta pivô + bomba (2+1)
        if stress > 50:
            return 2                      # corta bomba (2)
        if stress > 30:
            return 1                      # corta pivô (1)
        return 0                          # sem corte

    def gerente(self, est: dict, stress: float) -> int:
        """Regra: define teto de consumo pelo nível de estresse."""
        if stress > 70:
            return 0                      # conservador (20 kW)
        if stress > 35:
            return 1                      # moderado    (30 kW)
        return 2                          # liberal     (40 kW)
