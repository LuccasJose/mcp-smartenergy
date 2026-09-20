"""Estado operacional do MCP; reutiliza os componentes do motor."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..agents import AgentesHeuristicos, IQLSystem, SemAgente
from ..environment import FazendaEnergyEnv
from .tracker import MetricsTracker


@dataclass
class ServerState:
    """Uma analise ativa no processo, sem isolamento concorrente por cliente."""

    dias: list[pd.DataFrame]
    tarifa_24h: np.ndarray
    dataset_meta: dict
    iql: IQLSystem
    heuristico: AgentesHeuristicos
    sem_agente: SemAgente
    tracker: MetricsTracker
    env: FazendaEnergyEnv
    dia_atual_idx: int = 0
    soc_trace: float | None = None
    soc_trace_snapshot: float | None = None
    snapshots: dict[str, dict] = field(default_factory=dict)
    rl_padrao_travado: bool = False
    run_carregado: dict | None = None
    experimento_carregado: dict | None = None