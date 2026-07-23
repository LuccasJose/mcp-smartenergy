"""
AgenteFinanceiro — calcula índice de estresse financeiro (0–100) e
gerencia saldo de créditos solares (simplificado, 1 para 1).

Espelha smarty_energy/agents.AgenteFinanceiro.
"""

from config import CONFIG


class AgenteFinanceiro:
    def __init__(self, cfg: dict = CONFIG):
        self.cfg = cfg
        self.saldo_creditos = cfg["credito_inicial_kwh"]

    def calcular_estresse(self, tarifa: float, consumo_atual: float) -> float:
        """Estresse 0-100 baseado em tarifa, saldo e consumo atual no pico."""
        limiar = self.cfg["tarifa_estresse_limiar"]
        stress_tarifa = 70.0 if tarifa >= limiar else (tarifa / limiar) * 50.0
        pen_credito = 30.0 if self.saldo_creditos < 20 else 0.0
        agravante = 10.0 if (tarifa >= limiar and consumo_atual > 25.0) else 0.0
        return min(100.0, stress_tarifa + pen_credito + agravante)

    def atualizar_saldo(self, rede_kwh: float, excedente_kwh: float) -> None:
        """Saldo aumenta com excedente exportado, decresce com importação."""
        self.saldo_creditos += excedente_kwh
        self.saldo_creditos -= rede_kwh
        self.saldo_creditos = max(0.0, self.saldo_creditos)
