---
label: Componentes
icon: code-square
order: 60
---

# Componentes

O código-fonte vive em `src/smarty_energy/`.

```text
src/smarty_energy/
├── config.py        — Hiperparâmetros, pesos do reward, limites físicos
├── data_loader.py   — Base v8 (Sheets ou Excel) → DataFrames diários + metadados
├── agents.py        — AgenteQL, IQLSystem, heurístico, sem-agente, financeiro
├── environment.py   — FazendaEnergyEnv (simulador: estado → ações → reward)
├── training.py      — Loop IQL com early stopping (save-best)
├── evaluation.py    — Execução por dia, métricas mensais, cenários
├── metrics.py       — Métricas primárias do plano de testes (4.1/4.2)
├── runs.py          — Versionamento de treinos em outputs/runs/
├── benchmark.py     — RL × LLM: qualidade da decisão vs custo operacional
├── llm_policy.py    — Política de controle por LLM (tool-use)
├── mcp_server.py    — Servidor MCP mínimo do braço "LLM-via-MCP" do benchmark
├── visualization.py — Figuras do pipeline (outputs/plots/)
├── dashboard.py     — Dashboard Tkinter
├── dashboard_web.py — Dashboard web (Dash/Plotly)
└── mcp/             — Camada de serviço (ver "Servidor MCP")
    ├── server.py    — ~25 ferramentas para o LLM-juiz
    ├── tracker.py   — Métricas por passo/episódio
    └── dashboard/   — Cliente Streamlit
```

## Resumo de cada módulo

- **`config.py`** — fonte única de verdade dos parâmetros, incluindo os espaços
  de ação e o helper `ajustar_decay` (reescala o decaimento de ε para treinos
  curtos). Veja [Configuração](configuracao.md).
- **`data_loader.py`** — converte a planilha em uma lista de DataFrames (um por
  dia) e no vetor de tarifa horária; `descrever_base` gera os metadados usados
  pela tool `get_dataset_info`. Veja [Dados de entrada](dados.md).
- **`agents.py`** — `AgenteQL` (ε-greedy hysteretic, com série de TD-error para
  diagnóstico), `IQLSystem` (orquestra os três), `AgentesHeuristicos` e
  `SemAgente` (baselines) e `AgenteFinanceiro` (índice de estresse e créditos).
  `avaliar_politica` é o laço único de avaliação usado por todos.
- **`environment.py`** — simulador determinístico de 24 h: recebe as três ações,
  aplica as restrições HARD e o balanço de energia/bateria e devolve
  `(próximo_estado, reward, done, info)`, onde `info` é o registro horário
  completo.
- **`training.py`** — loop IQL: percorre os dias, atualiza as três Q-tables,
  decai ε e guarda o melhor checkpoint (early stopping). Aceita um `tracker`,
  o que permite ao servidor MCP reusar exatamente o mesmo treino.
- **`evaluation.py`** — roda cada braço nos 31 dias reais, calcula economia e
  dependência da rede, identifica e classifica cenários.
- **`metrics.py`** — definição operacional única das métricas do TCC
  (autossuficiência, autoconsumo, ciclos de bateria, gap de otimalidade).
- **`runs.py`** — cada treino vira `outputs/runs/<run_id>/` com Q-tables,
  histórico e `meta.json` (incluindo o CONFIG completo, para reprodutibilidade).
- **`visualization.py`** / **`dashboard*.py`** — figuras e as duas interfaces.

## Pontos de entrada

- [`main.py`](execucao.md) — dados → treino → avaliação → visualização → dashboard.
- [`server.py`](execucao-mcp.md) — servidor MCP com as ferramentas do LLM-juiz.
