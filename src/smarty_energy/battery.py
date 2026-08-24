"""Modelo fisico da bateria do ambiente SmartEnergy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BatteryFlow:
    """Resultado de uma operacao de carga ou descarga."""

    requested_kwh: float = 0.0
    input_kwh: float = 0.0
    stored_kwh: float = 0.0
    delivered_kwh: float = 0.0
    source: str | None = None
    blocked_reason: str | None = None


class BatteryModel:
    """Mantem o estado e aplica as restricoes fisicas da bateria.

    As entradas de carga sao medidas no lado AC. O throughput contabiliza a
    energia no lado DC, preservando a convencao do ambiente existente.
    """

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.reset()

    def reset(self, soc_inicial: float | None = None) -> None:
        self.soc_pct = (
            self.cfg["soc_inicial_pct"] if soc_inicial is None else soc_inicial
        )
        self.throughput_kwh = 0.0

    @property
    def capacity_kwh(self) -> float:
        return self.cfg["bateria_cap_kwh"]

    @property
    def soc_kwh(self) -> float:
        return self.soc_pct / 100.0 * self.capacity_kwh

    @property
    def soc_min_kwh(self) -> float:
        return self.cfg["soc_min_pct"] / 100.0 * self.capacity_kwh

    @property
    def soc_max_kwh(self) -> float:
        return self.cfg["soc_max_pct"] / 100.0 * self.capacity_kwh

    @property
    def throughput_remaining_kwh(self) -> float:
        return max(0.0, self.cfg["bat_throughput_max_kwh"] - self.throughput_kwh)

    def _update_soc(self, soc_kwh: float) -> None:
        soc_kwh = max(0.0, min(self.capacity_kwh, soc_kwh))
        self.soc_pct = soc_kwh / self.capacity_kwh * 100.0

    def charge(self, available_ac_kwh: float, source: str) -> BatteryFlow:
        """Armazena energia AC disponivel, respeitando eficiencia e limites."""
        requested = max(0.0, available_ac_kwh)
        if requested <= 0.0:
            return BatteryFlow(requested_kwh=requested, source=source,
                               blocked_reason="sem_energia_disponivel")
        if self.soc_kwh >= self.soc_max_kwh:
            return BatteryFlow(requested_kwh=requested, source=source,
                               blocked_reason="soc_maximo")
        if self.throughput_remaining_kwh <= 0.0:
            return BatteryFlow(requested_kwh=requested, source=source,
                               blocked_reason="throughput_esgotado")

        eta = self.cfg["eficiencia_carga"]
        stored = min(
            requested * eta,
            self.soc_max_kwh - self.soc_kwh,
            self.throughput_remaining_kwh,
        )
        input_kwh = stored / eta if eta > 0.0 else 0.0
        self._update_soc(self.soc_kwh + stored)
        self.throughput_kwh += stored
        return BatteryFlow(
            requested_kwh=requested,
            input_kwh=input_kwh,
            stored_kwh=stored,
            source=source,
        )

    def discharge(self, deficit_kwh: float, fraction: float) -> BatteryFlow:
        """Retira uma fracao do deficit e entrega energia AC a carga."""
        requested = max(0.0, deficit_kwh) * fraction
        if deficit_kwh <= 0.0:
            return BatteryFlow(requested_kwh=requested,
                               blocked_reason="sem_deficit")
        if self.soc_kwh <= self.soc_min_kwh:
            return BatteryFlow(requested_kwh=requested,
                               blocked_reason="soc_minimo")
        if self.throughput_remaining_kwh <= 0.0:
            return BatteryFlow(requested_kwh=requested,
                               blocked_reason="throughput_esgotado")

        eta = self.cfg["eficiencia_descarga"]
        withdrawn = min(
            requested / eta if eta > 0.0 else 0.0,
            self.soc_kwh - self.soc_min_kwh,
            self.throughput_remaining_kwh,
        )
        delivered = withdrawn * eta
        self._update_soc(self.soc_kwh - withdrawn)
        self.throughput_kwh += withdrawn
        return BatteryFlow(
            requested_kwh=requested,
            input_kwh=withdrawn,
            stored_kwh=withdrawn,
            delivered_kwh=delivered,
        )
