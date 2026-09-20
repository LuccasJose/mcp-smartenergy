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
├── battery.py       — BatteryModel: SoC, eficiência e throughput DC compartilhado
├── data_loader.py   — FEMS ou base v8 (Sheets/Excel) → DataFrames diários + metadados
├── agents.py        — AgenteQL, IQLSystem, heurístico, sem-agente, financeiro
├── environment.py   — FazendaEnergyEnv (simulador: estado → ações → reward)
├── training.py      — Loop IQL com seleção do melhor checkpoint greedy
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
    ├── server.py    — 41 ferramentas registradas para o LLM-juiz
    ├── state.py     — ServerState: componentes e marcadores da análise ativa
    ├── tracker.py   — Métricas por passo/episódio
    └── dashboard/   — Cliente Streamlit
```

## Resumo de cada módulo

- **`config.py`** — fonte única de verdade dos parâmetros, incluindo os espaços
  de ação e o helper `ajustar_decay` (reescala o decaimento de ε para treinos
  curtos). Veja [Configuração](configuracao.md).
- **`data_loader.py`** — converte FEMS ou planilha em uma lista de DataFrames (um por
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
- **`battery.py`** — único modelo de carga/descarga e limites da bateria,
  reutilizado pelo ambiente. Os [contratos do piloto](arquitetura.md) distinguem
  entradas AC, energia DC e reset diário.
- **`training.py`** — loop IQL: percorre os dias, atualiza as três Q-tables,
  decai ε e restaura o melhor checkpoint selecionado por avaliação greedy.
  Executa o horizonte configurado, sem parada antecipada. Aceita um `tracker`,
  o que permite ao servidor MCP reusar o mesmo treino.
- **`evaluation.py`** — roda cada braço nos dias fornecidos, calcula economia e
  dependência da rede, identifica e classifica cenários.
- **`metrics.py`** — definição operacional única das métricas do TCC
  (autossuficiência, autoconsumo, ciclos de bateria, gap de otimalidade).
- **`runs.py`** — cada treino vira `outputs/runs/<run_id>/` com Q-tables,
  histórico e `meta.json` (incluindo o CONFIG completo, para reprodutibilidade).
- **`visualization.py`** / **`dashboard*.py`** — figuras e as duas interfaces.
- **`mcp/server.py`** — registra tools na importação e cria o estado operacional
  em `initialize`, chamado por `main` antes do transporte. As tools acessam
  `ServerState` por `get_state`; há uma única referência ativa por processo.
  Veja os [contratos MCP](mcp.md) e ADR-002/003 no [plano](reorganizacao.md).
- **`mcp/state.py`** — contêiner tipado de dados, agentes, ambiente, tracker,
  snapshots e continuidade. Não duplica regras do motor nem isola clientes.

## Pontos de entrada

- [`main.py`](execucao.md) — dados → treino → avaliação → visualização → dashboard.
- [`server.py`](execucao-mcp.md) — servidor MCP com as ferramentas do LLM-juiz.
