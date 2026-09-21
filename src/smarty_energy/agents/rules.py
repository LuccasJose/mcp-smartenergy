"""Regras deterministicas de estresse financeiro e politicas de referencia."""

from ..config import CONFIG
from .evaluation import avaliar_politica


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
