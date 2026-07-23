"""Camada MCP do SmartEnergy.

`server.py` expõe o sistema multi-agente como ~25 ferramentas MCP
(configurar, treinar, avaliar, diagnosticar) para um LLM-juiz; `tracker.py`
acumula métricas por passo/episódio para essas ferramentas; `dashboard/`
é o cliente Streamlit que consome o servidor via HTTP.

Toda a física (ambiente, agentes, config, dados) vem do pacote pai
`smarty_energy` — esta camada não duplica nenhuma regra do modelo.
"""
