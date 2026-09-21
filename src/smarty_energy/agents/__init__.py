"""API publica dos agentes, preservada apos a separacao por responsabilidade.

Os consumidores continuam usando ``from smarty_energy.agents import ...``.
Implementacoes ficam em q_learning, rules, evaluation e system.
"""

from .evaluation import avaliar_politica
from .q_learning import AgenteQL, construir_agentes
from .rules import AgenteFinanceiro, AgentesHeuristicos, SemAgente
from .system import IQLSystem

__all__ = [
    "AgenteQL", "construir_agentes", "AgenteFinanceiro",
    "AgentesHeuristicos", "SemAgente", "avaliar_politica", "IQLSystem",
]
