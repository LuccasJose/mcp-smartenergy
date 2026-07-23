"""Fixtures da suite da camada MCP.

Ficam em um diretorio proprio (com conftest proprio) porque tem os mesmos
nomes das fixtures de `tests/conftest.py` com valores diferentes: aqui o dia
sintetico usa a bomba no nominal (15 kW) para exercitar teto e PCC, enquanto
a suite do pacote usa cargas menores.

Usamos dia sintetico em vez do dataset real para isolar testes de I/O.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Torna o pacote src/ importavel mesmo sem instalacao (idem tests/conftest.py)
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "src"))

from smarty_energy.config import CONFIG
from smarty_energy.environment import FazendaEnergyEnv
from smarty_energy.agents import IQLSystem, AgenteQL
from smarty_energy.mcp.tracker import MetricsTracker


@pytest.fixture
def cfg() -> dict:
    """CONFIG copiado para isolar mutacoes entre testes."""
    return dict(CONFIG)


@pytest.fixture
def tarifa_fake() -> np.ndarray:
    """Tarifa fora-pico R$0.70 com pico R$1.10 das 18h as 20h."""
    t = np.full(24, 0.70)
    t[18:21] = 1.10
    return t


@pytest.fixture
def dia_fake() -> pd.DataFrame:
    """Dia sintetico com geracao e consumo constantes.

    Inclui `secador_kw` (coluna da base v8): sem ela o env cairia sempre no
    rescue do secador e as asserticoes de potencia mudariam.
    """
    return pd.DataFrame({
        "hora":        list(range(24)),
        "solar_kw":    [10.0] * 24,
        "eolico_kw":   [2.0] * 24,
        "pivo_kw":     [3.0] * 24,
        "captacao_kw": [15.0] * 24,
        "sede_kw":     [1.0] * 24,
        "secador_kw":  [1.5] * 24,
        "silo_kw":     [0.5] * 24,
        "data":        pd.Timestamp("2025-01-01"),
    })


@pytest.fixture
def dia_solar_forte() -> pd.DataFrame:
    """Dia com sol intenso para testes de bonus_pivo_solar e carga de bateria."""
    solar = [0.0]*6 + [20.0, 30.0, 40.0, 45.0, 48.0, 50.0,
                       50.0, 48.0, 40.0, 30.0, 20.0, 10.0,
                       5.0] + [0.0]*5
    return pd.DataFrame({
        "hora":        list(range(24)),
        "solar_kw":    solar,
        "eolico_kw":   [2.0] * 24,
        "pivo_kw":     [3.0] * 24,
        "captacao_kw": [15.0] * 24,
        "sede_kw":     [1.0] * 24,
        "secador_kw":  [1.5] * 24,
        "silo_kw":     [0.5] * 24,
        "data":        pd.Timestamp("2025-01-02"),
    })


@pytest.fixture
def env(dia_fake, tarifa_fake, cfg) -> FazendaEnergyEnv:
    return FazendaEnergyEnv(dia_fake, tarifa_fake, cfg)


@pytest.fixture
def env_solar(dia_solar_forte, tarifa_fake, cfg) -> FazendaEnergyEnv:
    return FazendaEnergyEnv(dia_solar_forte, tarifa_fake, cfg)


@pytest.fixture
def iql(cfg) -> IQLSystem:
    return IQLSystem(cfg)


@pytest.fixture
def tracker() -> MetricsTracker:
    return MetricsTracker()
