import json
import numpy as np
from collections import defaultdict
from config import (
    N_ACOES_CONSUMO, N_ACOES_GERENTE, N_ACOES_TOTAL,
    DEFAULT_HYPERPARAMS, SOC_MINIMO,
)


class AgenteQL:
    """
    Agente Q-learning histérico para gestão de energia.

    Hysteretic Q-learning: usa alpha (otimista) para atualizações positivas
    e beta (pessimista, beta << alpha) para negativas. Estabiliza ambientes
    com múltiplos agentes ou recompensas não-estacionárias.

    Espaço de ações combinado: a_arm × a_cons × a_ger = 3 × 8 × 3 = 72 ações.
    """

    def __init__(
        self,
        n_episodios: int = DEFAULT_HYPERPARAMS["n_episodios"],
        alpha: float = DEFAULT_HYPERPARAMS["alpha"],
        gamma: float = DEFAULT_HYPERPARAMS["gamma"],
        beta: float = DEFAULT_HYPERPARAMS["beta"],
        epsilon_inicial: float = DEFAULT_HYPERPARAMS["epsilon_inicial"],
        epsilon_final: float = DEFAULT_HYPERPARAMS["epsilon_final"],
        epsilon_decay: float = DEFAULT_HYPERPARAMS["epsilon_decay"],
    ):
        self.n_episodios = n_episodios
        self.alpha = alpha
        self.gamma = gamma
        self.beta = beta
        self.epsilon_inicial = epsilon_inicial
        self.epsilon_final = epsilon_final
        self.epsilon_decay = epsilon_decay

        # Q-table: state_tuple -> array[N_ACOES_TOTAL]
        self.q_table: dict[tuple, np.ndarray] = defaultdict(
            lambda: np.zeros(N_ACOES_TOTAL, dtype=np.float64)
        )

        # RNG encapsulado para reprodutibilidade
        self.rng = np.random.default_rng()

        # Métricas do agente
        self.epsilon = epsilon_inicial
        self.n_updates: int = 0

        # Histórico de treino
        self.rewards_hist: list[float] = []
        self.custos_hist: list[float] = []
        self.epsilons: list[float] = []

    # ------------------------------------------------------------------ #
    # Discretização do estado                                              #
    # ------------------------------------------------------------------ #

    def discretize(self, obs: dict) -> tuple:
        """Converte obs contínua em tupla discreta para indexar a Q-table."""
        hora = int(obs["hora"])
        soc_bucket = int(min(obs["soc"] * 5, 4))           # 0–4
        em_pico = int(obs["em_pico_tarifa"])                # 0–1

        g = obs["geracao_kw"]
        if g < 8.0:
            ger_bucket = 0
        elif g < 22.0:
            ger_bucket = 1
        else:
            ger_bucket = 2

        c = obs["consumo_base_kw"]
        if c < 30.0:
            cons_bucket = 0
        elif c < 55.0:
            cons_bucket = 1
        else:
            cons_bucket = 2

        # horas que a bomba já operou hoje: <2h, 2–3h, ≥4h
        hb = obs.get("horas_bomba_hoje", 0)
        bomba_bucket = 0 if hb < 2 else (1 if hb < 4 else 2)

        return (hora, soc_bucket, em_pico, ger_bucket, cons_bucket, bomba_bucket)
        # Espaço: 24 × 5 × 2 × 3 × 3 × 3 = 6 480 estados

    # ------------------------------------------------------------------ #
    # Codificação de ações                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def encode_action(a_arm: int, a_cons: int, a_ger: int) -> int:
        return a_arm * (N_ACOES_CONSUMO * N_ACOES_GERENTE) + a_cons * N_ACOES_GERENTE + a_ger

    @staticmethod
    def decode_action(action_id: int) -> tuple[int, int, int]:
        a_arm = action_id // (N_ACOES_CONSUMO * N_ACOES_GERENTE)
        rem = action_id % (N_ACOES_CONSUMO * N_ACOES_GERENTE)
        a_cons = rem // N_ACOES_GERENTE
        a_ger = rem % N_ACOES_GERENTE
        return a_arm, a_cons, a_ger

    # ------------------------------------------------------------------ #
    # Política                                                             #
    # ------------------------------------------------------------------ #

    def choose_action(self, state: tuple, explore: bool = True) -> int:
        if explore and self.rng.random() < self.epsilon:
            return int(self.rng.integers(N_ACOES_TOTAL))
        return int(np.argmax(self.q_table[state]))

    # ------------------------------------------------------------------ #
    # Atualização histérica                                                #
    # ------------------------------------------------------------------ #

    def update(
        self,
        state: tuple,
        action: int,
        reward: float,
        next_state: tuple,
        done: bool,
    ):
        q_atual = self.q_table[state][action]

        if done:
            q_alvo = reward
        else:
            q_alvo = reward + self.gamma * float(np.max(self.q_table[next_state]))

        delta = q_alvo - q_atual

        # Hysteretic: alpha para melhorias, beta para degradações
        lr = self.alpha if delta >= 0.0 else self.beta
        self.q_table[state][action] += lr * delta
        self.n_updates += 1

    def _decay_epsilon(self):
        self.epsilon = max(self.epsilon_final, self.epsilon * self.epsilon_decay)

    # ------------------------------------------------------------------ #
    # Loop de treino                                                       #
    # ------------------------------------------------------------------ #

    def train(self, env, tracker=None) -> dict:
        """
        Treina o agente por self.n_episodios episódios.
        Retorna sumário das métricas de treino.
        """
        self.rewards_hist.clear()
        self.custos_hist.clear()
        self.epsilons.clear()
        self.epsilon = self.epsilon_inicial

        for ep in range(self.n_episodios):
            obs = env.reset()
            state = self.discretize(obs)
            reward_ep = 0.0
            custo_ep = 0.0
            done = False

            while not done:
                action_id = self.choose_action(state, explore=True)
                a_arm, a_cons, a_ger = self.decode_action(action_id)
                next_obs, reward, done, info = env.step(a_arm, a_cons, a_ger)
                next_state = self.discretize(next_obs)

                self.update(state, action_id, reward, next_state, done)

                state = next_state
                reward_ep += reward
                custo_ep += info["custo_r"]

            self._decay_epsilon()
            self.rewards_hist.append(reward_ep)
            self.custos_hist.append(custo_ep)
            self.epsilons.append(self.epsilon)

            if tracker:
                tracker.fechar_episodio(
                    agente="ql_treino",
                    reward_total=reward_ep,
                    custo_total=custo_ep,
                    epsilon=self.epsilon,
                    cenario=getattr(env, "cenario_dia", "EQUILIBRADO"),
                )

        return self._sumario_treino()

    # ------------------------------------------------------------------ #
    # Loop de avaliação                                                    #
    # ------------------------------------------------------------------ #

    def evaluate(self, env, n_dias: int = 30, tracker=None) -> dict:
        """
        Avalia a política greedy por n_dias (sem exploração).
        Retorna métricas mensais.
        """
        custos, redes, violacoes_soc, rewards = [], [], [], []

        for _ in range(n_dias):
            obs = env.reset()
            state = self.discretize(obs)
            custo_dia = 0.0
            rede_dia = 0.0
            viols_soc = 0
            reward_dia = 0.0
            done = False

            while not done:
                action_id = self.choose_action(state, explore=False)
                a_arm, a_cons, a_ger = self.decode_action(action_id)
                next_obs, reward, done, info = env.step(a_arm, a_cons, a_ger)
                next_state = self.discretize(next_obs)

                if tracker:
                    tracker.registrar_passo(info, agente="ql_eval")

                state = next_state
                custo_dia += info["custo_r"]
                rede_dia += info["rede_kwh"]
                reward_dia += info["reward"]
                if info["soc"] < SOC_MINIMO:
                    viols_soc += 1

            custos.append(custo_dia)
            redes.append(rede_dia)
            violacoes_soc.append(viols_soc)
            rewards.append(reward_dia)

            if tracker:
                tracker.fechar_episodio(
                    agente="ql_eval",
                    reward_total=reward_dia,
                    custo_total=custo_dia,
                    epsilon=0.0,
                    cenario=getattr(env, "cenario_dia", "EQUILIBRADO"),
                )

        return {
            "n_dias": n_dias,
            "custo_medio_dia_rs": float(np.mean(custos)),
            "custo_std": float(np.std(custos)),
            "rede_media_dia_kwh": float(np.mean(redes)),
            "violacoes_soc_media_h_dia": float(np.mean(violacoes_soc)),
            "reward_medio_dia": float(np.mean(rewards)),
        }

    # ------------------------------------------------------------------ #
    # Métricas do agente                                                   #
    # ------------------------------------------------------------------ #

    def get_qtable_info(self) -> dict:
        return {
            "n_estados": len(self.q_table),
            "n_updates": self.n_updates,
            "epsilon": float(self.epsilon),
            "alpha": self.alpha,
            "gamma": self.gamma,
            "beta": self.beta,
            "n_episodios_config": self.n_episodios,
        }

    def save_qtable(self, filepath: str):
        """Salva Q-table em JSON. Chaves de tuple são serializadas como strings."""
        data = {
            "hyperparams": {
                "alpha": self.alpha, "gamma": self.gamma, "beta": self.beta,
                "epsilon": float(self.epsilon),
                "epsilon_inicial": self.epsilon_inicial,
                "epsilon_final": self.epsilon_final,
                "epsilon_decay": self.epsilon_decay,
                "n_episodios": self.n_episodios,
            },
            "n_updates": self.n_updates,
            "qtable": {str(k): v.tolist() for k, v in self.q_table.items()},
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def load_qtable(self, filepath: str):
        """Carrega Q-table de JSON salvo por save_qtable."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.n_updates = data.get("n_updates", 0)
        self.q_table = defaultdict(lambda: np.zeros(N_ACOES_TOTAL, dtype=np.float64))
        for k_str, v in data["qtable"].items():
            # converte "('1', '2', ...)" de volta para tuple de ints
            key = tuple(int(x) for x in k_str.strip("()").split(", "))
            self.q_table[key] = np.array(v, dtype=np.float64)
        if "hyperparams" in data:
            hp = data["hyperparams"]
            self.epsilon = hp.get("epsilon", self.epsilon)

    def _sumario_treino(self) -> dict:
        n = len(self.rewards_hist)
        if n == 0:
            return {}
        janela = min(50, n)
        return {
            "episodios_treinados": n,
            "reward_ultimo_ep": float(self.rewards_hist[-1]),
            "reward_media_ultimos_50ep": float(np.mean(self.rewards_hist[-janela:])),
            "custo_medio_ultimos_50ep_rs": float(np.mean(self.custos_hist[-janela:])),
            "epsilon_final": float(self.epsilon),
            "n_updates_total": self.n_updates,
            "n_estados_visitados": len(self.q_table),
        }
