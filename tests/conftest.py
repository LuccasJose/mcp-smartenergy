"""Fixtures e utilitários compartilhados pela suíte de testes.

Objetivos:
- Tornar `src/smarty_energy` importável sem instalar o pacote.
- Fornecer dados reais **offline e determinísticos** (força o Excel local,
  ignorando o `SHEET_ID` do `.env` que baixaria do Google Drive).
- Fornecer dados sintéticos controlados para testes de unidade.
- Fornecer um helper de treino curto/configurável para os testes de
  integração (número de episódios via env var `SMARTY_TEST_EPISODIOS`).
"""

import copy
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ── Torna o pacote src/ importável mesmo sem instalação ───────────────
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from smarty_energy import data_loader
from smarty_energy.config import CONFIG
from smarty_energy.agents import AgenteQL
from smarty_energy.training import treinar

# Semente global para reprodutibilidade dos testes.
SEED = 42


@pytest.fixture(autouse=True)
def _semente_determinista():
    """Fixa a semente do NumPy antes de cada teste (determinismo)."""
    np.random.seed(SEED)
    yield


@pytest.fixture(scope="session", autouse=True)
def _isola_outputs(tmp_path_factory):
    """Redireciona a escrita de artefatos do treino para um diretório temporário.

    Sem isso, rodar a suíte sobrescreveria `outputs/models/training_history.pkl`
    (e Q-tables) do treino real do usuário.
    """
    import smarty_energy.training as training_mod
    original = training_mod.OUTPUT_DIR
    training_mod.OUTPUT_DIR = tmp_path_factory.mktemp("outputs_test")
    yield
    training_mod.OUTPUT_DIR = original


# ── Dados reais ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def dados_reais():
    """Carrega a base real do projeto (31 dias) uma vez por sessão.

    Usa o loader oficial `carregar_dados()`, que respeita o `SHEET_ID`
    do `.env` (Google Sheets) ou o `DATA_PATH` local, conforme configurado.
    Faz *skip* se a base não puder ser carregada (sem rede / sem arquivo /
    esquema incompatível), evitando falhas em ambientes sem acesso à base.
    """
    try:
        dias, tarifa = data_loader.carregar_dados()
    except Exception as exc:  # noqa: BLE001 — skip em qualquer falha de dados
        pytest.skip(f"Base de dados real indisponível: {exc}")
    if not dias:
        pytest.skip("Base de dados real vazia.")
    return dias, tarifa


@pytest.fixture(scope="session")
def dias_reais(dados_reais):
    return dados_reais[0]


@pytest.fixture(scope="session")
def tarifa_real(dados_reais):
    return dados_reais[1]


# ── Dados sintéticos (unidade) ────────────────────────────────────────

@pytest.fixture
def tarifa_fake() -> np.ndarray:
    """Tarifa constante de R$0,70 com pico de R$1,10 das 18h às 20h."""
    t = np.full(24, 0.70)
    t[18:21] = 1.10
    return t


@pytest.fixture
def dia_fake() -> pd.DataFrame:
    """Dia sintético com geração e consumo constantes (inclui secador)."""
    return pd.DataFrame({
        "hora"       : range(24),
        "solar_kw"   : [10.0] * 24,
        "eolico_kw"  : [2.0]  * 24,
        "pivo_kw"    : [5.0]  * 24,
        "captacao_kw": [3.0]  * 24,
        "sede_kw"    : [1.0]  * 24,
        "secador_kw" : [1.5]  * 24,
        "silo_kw"    : [0.5]  * 24,
        "data"       : pd.Timestamp("2025-01-01"),
    })


@pytest.fixture
def env(dia_fake, tarifa_fake):
    from smarty_energy.environment import FazendaEnergyEnv
    return FazendaEnergyEnv(dia_fake, tarifa_fake, CONFIG)


# ── Treino configurável para integração ───────────────────────────────

def n_episodios_teste() -> int:
    """Número de episódios do treino de teste.

    Padrão: 800 (rápido, mas suficiente para o RL superar 'sem agente').
    Sobrescreva com a env var `SMARTY_TEST_EPISODIOS` para o teste completo:

        $env:SMARTY_TEST_EPISODIOS = "100000"; pytest -m slow
    """
    try:
        return max(1, int(os.getenv("SMARTY_TEST_EPISODIOS", "800")))
    except ValueError:
        return 800


def config_teste(n_ep: int) -> dict:
    """Copia o CONFIG e ajusta para um treino de `n_ep` episódios.

    Reescala o decaimento de epsilon para que a exploração chegue perto
    de `epsilon_final` ao fim do treino — sem isso, treinos curtos
    ficariam quase 100% aleatórios e o RL não aprenderia nada útil.
    """
    cfg = copy.deepcopy(CONFIG)
    cfg["n_episodios"] = n_ep
    eps_i = cfg["epsilon_inicial"]
    eps_f = cfg["epsilon_final"]
    # decay^n_ep ≈ eps_f/eps_i  →  decay = (eps_f/eps_i)^(1/n_ep)
    cfg["epsilon_decay"] = (eps_f / eps_i) ** (1.0 / max(1, n_ep))
    return cfg


def treinar_agentes(dias, tarifa, n_ep: int, seed: int = SEED) -> dict:
    """Cria e treina os 3 agentes de forma determinística."""
    np.random.seed(seed)
    cfg = config_teste(n_ep)
    agentes = {
        "armazenamento": AgenteQL(3, "Armazenamento", cfg),
        "consumo"      : AgenteQL(8, "Consumo",        cfg),
        "gerente"      : AgenteQL(3, "Gerente",        cfg),
    }
    treinar(dias, tarifa, agentes, cfg)
    return agentes


@pytest.fixture(scope="session")
def agentes_treinados(dados_reais):
    """Agentes treinados uma única vez por sessão (reuso entre testes)."""
    dias, tarifa = dados_reais
    return treinar_agentes(dias, tarifa, n_episodios_teste())


@pytest.fixture(scope="session")
def treino_fn():
    """Expõe o helper de treino determinístico para os testes."""
    return treinar_agentes


@pytest.fixture(scope="session")
def n_ep_teste():
    """Número de episódios do treino de teste (configurável por env var)."""
    return n_episodios_teste()


@pytest.fixture(scope="session")
def seed_teste():
    return SEED
