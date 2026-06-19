"""Fixtures comuns para os testes.

Usamos dia sintetico em vez do dataset real para isolar testes de I/O.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Garante que a raiz do projeto esta no path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import CONFIG
from environment.energy_env import FazendaEnergyEnv
from agents.qlearning_agent import IQLSystem, AgenteQL
from metrics.tracker import MetricsTracker


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
    """Dia sintetico com geracao e consumo constantes."""
    return pd.DataFrame({
        "hora":        list(range(24)),
        "solar_kw":    [10.0] * 24,
        "eolico_kw":   [2.0] * 24,
        "pivo_kw":     [3.0] * 24,
        "captacao_kw": [15.0] * 24,
        "sede_kw":     [1.0] * 24,
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
