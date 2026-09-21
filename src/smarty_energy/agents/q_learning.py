"""Q-learning histeretico e construcao da topologia cooperativa."""

import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..config import CONFIG, N_ACOES_ARMAZENAMENTO, N_ACOES_CONSUMO, N_ACOES_GERENTE


class AgenteQL:
    """Agente de Q-Learning com política epsilon-greedy.

    Todos os agentes recebem o mesmo reward cooperativo do ambiente,
    alinhando o aprendizado individual ao objetivo global.
    """

    def __init__(self, n_acoes: int, nome: str = "ql", cfg: dict = CONFIG):
        self.n_acoes   = n_acoes
        self.nome      = nome
        self.cfg       = cfg
        self.epsilon   = cfg["epsilon_inicial"]
        self.alpha     = cfg["alpha"]
        self.beta      = cfg.get("beta", 0.01)  # taxa de aprendizado pessimista (Hysteretic)
        self.gamma     = cfg["gamma"]
        self.eps_min   = cfg["epsilon_final"]
        self.eps_decay = cfg["epsilon_decay"]
        self.q_table   = defaultdict(lambda: np.zeros(n_acoes))
        self.n_updates = 0
        # Janela rolante de TD-errors para diagnóstico de convergência
        # (lida por `td_error_recente` e pela tool MCP get_td_error_series).
        self.td_errors: list[float] = []
        self.td_errors_max_len = 5000

    def agir(self, estado_disc: tuple, explorando: bool = True) -> int:
        """Seleciona uma ação via política epsilon-greedy.

        Usa o RNG global do NumPy de propósito: a suíte de testes fixa
        `np.random.seed` para tornar treinos curtos reprodutíveis.
        """
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
        self.td_errors.append(float(td_error))
        if len(self.td_errors) > self.td_errors_max_len:
            del self.td_errors[:-self.td_errors_max_len]

    def decair_epsilon(self) -> None:
        """Reduz epsilon multiplicativamente (decaimento exponencial)."""
        self.epsilon = max(self.eps_min, self.epsilon * self.eps_decay)

    @property
    def n_estados(self) -> int:
        """Número de estados distintos visitados."""
        return len(self.q_table)

    def td_error_recente(self, janela: int = 500) -> dict:
        """Média e desvio do |TD-error| na janela final — proxy de convergência."""
        if not self.td_errors:
            return {"janela": 0, "td_abs_medio": 0.0, "td_std": 0.0}
        amostra = self.td_errors[-janela:]
        return {
            "janela": len(amostra),
            "td_abs_medio": float(np.mean(np.abs(amostra))),
            "td_std": float(np.std(amostra)),
        }

    def get_info(self) -> dict:
        """Resumo do agente para diagnóstico (tools MCP e health_report)."""
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
        """Persiste a Q-table em disco via pickle."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"q_table": dict(self.q_table), "epsilon": self.epsilon,
                         "n_updates": self.n_updates, "nome": self.nome,
                         "n_acoes": self.n_acoes}, f)

    def load(self, path: str | Path) -> None:
        """Carrega uma Q-table salva anteriormente."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        # Guarda de compatibilidade: um run salvo com outro espaço de ações
        # produziria índices inválidos no argmax. Runs legados não gravavam
        # n_acoes (None) — nesse caso mantém o valor esperado.
        n_salvo = data.get("n_acoes")
        if n_salvo is not None and n_salvo != self.n_acoes:
            raise ValueError(
                f"Q-table '{self.nome}' salva com n_acoes={n_salvo}, esperado "
                f"{self.n_acoes}. Espaço de ações incompatível — recarregar "
                "produziria uma política inválida."
            )
        self.n_acoes   = n_salvo if n_salvo is not None else self.n_acoes
        self.q_table   = defaultdict(lambda: np.zeros(self.n_acoes), data["q_table"])
        self.epsilon   = data.get("epsilon", self.epsilon)
        self.n_updates = data.get("n_updates", 0)


def construir_agentes(cfg: dict = CONFIG) -> dict:
    """Instancia os três agentes Q-Learning com os tamanhos de ação padrão.

    Fonte única da topologia dos agentes — usada pelo treino do pipeline, pelo
    IQLSystem do servidor MCP e ao recarregar um run salvo para revisualização.
    Os nomes em minúsculas casam com o padrão de arquivo `qtable_<nome>.pkl`
    usado por `runs.salvar_run`, tornando as Q-tables intercambiáveis entre os
    dois caminhos de treino.
    """
    return {
        "armazenamento": AgenteQL(N_ACOES_ARMAZENAMENTO, "armazenamento", cfg),
        "consumo"      : AgenteQL(N_ACOES_CONSUMO,       "consumo",       cfg),
        "gerente"      : AgenteQL(N_ACOES_GERENTE,       "gerente",       cfg),
    }
