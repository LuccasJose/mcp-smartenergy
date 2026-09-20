"""
Agentes do sistema SmartEnergy MAS.

AgenteQL           — Q-Learning independente (IQL) com política epsilon-greedy.
IQLSystem          — Orquestra os 3 agentes (treino/avaliação com SOC propagado).
AgenteFinanceiro   — Índice de estresse financeiro + saldo de créditos.
AgentesHeuristicos — Baseline baseado em regras (sem aprendizado).
SemAgente          — Baseline "fazenda como está hoje" (sem gestão nenhuma).
"""

import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np

from .config import (
    CONFIG, N_ACOES_ARMAZENAMENTO, N_ACOES_CONSUMO, N_ACOES_GERENTE,
)


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

    def __init__(self, cfg: dict = CONFIG):
        self.cfg = cfg

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
        if soc > self.cfg["soc_max_pct"]:
            return 1                      # cheio → manter
        if soc < self.cfg["soc_min_pct"] + 2:
            return 1                      # crítico → não forçar descarga
        if tarifa > 0.9:
            return 4                      # pico tarifário → descarregar tudo
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

    def agir(self, est: dict) -> tuple[int, int, int]:
        """As três ações da hora, a partir do estresse financeiro do estado."""
        stress = self.stress_financeiro(est)
        return self.armazenamento(est), self.consumo(est, stress), self.gerente(est, stress)

    def avaliar(self, dias, tarifa_24h, env_cls=None, *, n_dias: int = 30,
                tracker=None, tracker_key: str = "heuristico",
                propagar_soc: bool = True,
                soc_inicial: float | None = None) -> dict:
        """Roda o baseline heurístico em `n_dias` (ver `avaliar_politica`)."""
        return avaliar_politica(
            lambda env, est: self.agir(est), dias, tarifa_24h, cfg=self.cfg,
            env_cls=env_cls, n_dias=n_dias, tracker=tracker,
            tracker_key=tracker_key, propagar_soc=propagar_soc,
            soc_inicial=soc_inicial,
        )


class SemAgente:
    """Cenário sem gestão nenhuma — a fazenda 'como está hoje'.

    Sem otimização: a bateria nunca é despachada (inerte), o teto é liberal,
    o secador segue o cronograma bruto da base e o pivô só começa no fim da
    tarde — as 8h de irrigação (16-23h) atravessam o pico tarifário 18-20h
    inteiro, sem sol para compensar. É a referência C0 do plano de testes;
    a versão de dia único é `evaluation.rodar_sem_agente`.
    """

    PIVO_HORA_INICIO = 16  # irrigação tardia — atravessa o pico 18-20h inteiro

    def __init__(self, cfg: dict = CONFIG):
        self.cfg = cfg

    def agir(self, est: dict) -> tuple[int, int, int]:
        a_cons = 1 if est["hora"] < self.PIVO_HORA_INICIO else 0
        return (1, a_cons, 2)         # bateria inerte, teto liberal

    def avaliar(self, dias, tarifa_24h, env_cls=None, *, n_dias: int = 30,
                tracker=None, tracker_key: str = "sem_agente",
                propagar_soc: bool = True,
                soc_inicial: float | None = None) -> dict:
        """Roda o baseline sem gestão em `n_dias` (ver `avaliar_politica`)."""
        return avaliar_politica(
            lambda env, est: self.agir(est), dias, tarifa_24h, cfg=self.cfg,
            env_cls=env_cls, n_dias=n_dias, tracker=tracker,
            tracker_key=tracker_key, propagar_soc=propagar_soc,
            soc_inicial=soc_inicial,
        )


# ──────────────────────────────────────────────────────────────
# Harness de avaliação compartilhado
# ──────────────────────────────────────────────────────────────

def avaliar_politica(escolher, dias, tarifa_24h, *, cfg: dict = CONFIG,
                     env_cls=None, n_dias: int = 30, tracker=None,
                     tracker_key: str = "politica",
                     propagar_soc: bool = True,
                     soc_inicial: float | None = None,
                     reiniciar_soc_em: frozenset[int] = frozenset()) -> dict:
    """Roda uma política por `n_dias` e devolve as métricas médias diárias.

    Fonte única do laço de avaliação — IQL, heurístico e sem-agente usam este
    mesmo caminho, garantindo que as métricas sejam comparáveis (mesmo env,
    mesmos dias, mesma propagação de SOC).

    Args:
        escolher     : callable ``(env, est) -> (a_arm, a_cons, a_ger)``.
        env_cls      : classe do ambiente; None usa `FazendaEnergyEnv`
                       (import tardio para evitar ciclo com environment.py).
        propagar_soc : se True, o SOC final de um dia inicia o dia seguinte.
        soc_inicial  : SOC do 1º dia; None usa `cfg['soc_inicial_pct']` (50%).
                       Permite continuar do SOC final do treino.
        reiniciar_soc_em : indices de dias que iniciam blocos independentes;
                   nesses indices o SOC volta ao valor inicial, inclusive no wrap.
        tracker      : `mcp.tracker.MetricsTracker` opcional, alimentado passo
                       a passo e por episódio.
    """
    if env_cls is None:
        from .environment import FazendaEnergyEnv
        env_cls = FazendaEnergyEnv

    custos, redes, viols_soc, rewards = [], [], [], []
    soc_primeiro = cfg["soc_inicial_pct"] if soc_inicial is None else float(soc_inicial)
    soc_proximo  = soc_primeiro
    soc_final    = soc_primeiro

    for ep in range(n_dias):
        if ep % len(dias) in reiniciar_soc_em:
            soc_proximo = soc_primeiro
        env = env_cls(dias[ep % len(dias)], tarifa_24h, cfg)
        est = env.reset(soc_inicial=soc_proximo)

        custo_dia = rede_dia = reward_dia = 0.0
        viols = 0
        for _ in range(24):
            a_arm, a_cons, a_ger = escolher(env, est)
            est, reward, done, info = env.step(a_arm, a_cons, a_ger)
            custo_dia  += info["custo_r"]
            rede_dia   += info["rede_kwh"]
            reward_dia += info["reward"]
            if info["soc"] < cfg["soc_min_pct"]:
                viols += 1
            if tracker:
                tracker.registrar_passo(info, agente=tracker_key)
            if done:
                break

        if propagar_soc:
            soc_proximo = env.soc
        soc_final = env.soc

        custos.append(custo_dia)
        redes.append(rede_dia)
        viols_soc.append(viols)
        rewards.append(reward_dia)

        if tracker:
            tracker.fechar_episodio(
                agente=tracker_key, reward_total=reward_dia,
                custo_total=custo_dia, epsilon=0.0, cenario="REAL",
            )

    return {
        "n_dias": n_dias,
        "soc_inicial_pct": float(soc_primeiro),
        "soc_final_pct": float(soc_final),
        "custo_medio_dia_rs": float(np.mean(custos)),
        "custo_std": float(np.std(custos)),
        "rede_media_dia_kwh": float(np.mean(redes)),
        "violacoes_soc_media_h_dia": float(np.mean(viols_soc)),
        "reward_medio_dia": float(np.mean(rewards)),
    }


# ──────────────────────────────────────────────────────────────
# Orquestração IQL (usada pelo servidor MCP)
# ──────────────────────────────────────────────────────────────

class IQLSystem:
    """Orquestra os 3 agentes independentes (armazenamento, consumo, gerente).

    É a API de alto nível consumida pelo servidor MCP: agir/aprender em bloco,
    reconfigurar hiperparâmetros em runtime, treinar e avaliar. O treino delega
    a `training.treinar` — mesmo laço, mesmo early stopping do pipeline offline.
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

        Delega a `training.treinar` (early stopping com save-best incluído),
        reescalando o decaimento de ε para o horizonte pedido — sem isso, um
        treino curto de servidor herdaria o decay calibrado para 100k episódios
        e os agentes ficariam aleatórios até o fim. Se alguém fixou
        `epsilon_decay` via `reconfigurar`, esse valor é respeitado.

        A seleção do checkpoint usa um subconjunto held-out dos dias (~1/3),
        não o mês inteiro — assim a política escolhida não é a que melhor se
        ajusta ao MESMO conjunto em que os resultados serão reportados
        (evita o viés otimista de "selecionar no conjunto de teste").
        """
        from .config import ajustar_decay
        from .training import treinar as treinar_loop

        if self.decay_manual:
            cfg = {**self.cfg, "n_episodios": self.n_episodios}
        else:
            cfg = ajustar_decay(self.cfg, self.n_episodios)
            for ag in self.agentes.values():
                ag.eps_decay = cfg["epsilon_decay"]
        # Held-out de seleção: 1 a cada 3 dias (treina em todos, seleciona nestes).
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
