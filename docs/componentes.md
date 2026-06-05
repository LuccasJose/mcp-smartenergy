---
label: Componentes
icon: code-square
order: 60
---

# Componentes

O código-fonte vive em `src/smarty_energy/`.

```text
src/smarty_energy/
├── config.py        — Hiperparâmetros (alpha, gamma, epsilon, pesos, bateria)
├── data_loader.py   — Leitura do Excel (Tarifa, Geracao, Cargas) → DataFrames diários
├── agents.py        — AgenteQL (Q-Learning ε-greedy) + AgentesHeuristicos (baseline)
├── environment.py   — FazendaEnergyEnv (simulador Gym-like: estado → ações → reward)
├── training.py      — Loop IQL: amostra dia, simula 24h, atualiza os 3 agentes, decai ε
├── evaluation.py    — Roda heurístico e RL em dias reais; métricas mensais; cenários
├── visualization.py — Plots (curvas, comparativo, cenários) salvos em outputs/plots/
└── dashboard.py     — Interface visual (Tkinter) exibida ao final do pipeline
```

## Resumo de cada módulo

- **`config.py`** — fonte única de verdade dos parâmetros. Veja [Configuração](configuracao.md).
- **`data_loader.py`** — converte a planilha em uma lista de DataFrames (um por
  dia) e no vetor de tarifa horária. Veja [Dados de entrada](dados.md).
- **`agents.py`** — `AgenteQL` implementa ε-greedy com decaimento; `AgentesHeuristicos`
  é o baseline de regras com índice de estresse financeiro.
- **`environment.py`** — simulador determinístico de 24 h: recebe as três ações,
  aplica balanço de energia/bateria e devolve `(próximo_estado, reward, done, info)`.
- **`training.py`** — orquestra o IQL (Independent Q-Learning): a cada episódio
  sorteia um dia, simula as 24 horas e atualiza as três Q-tables.
- **`evaluation.py`** — compara RL e heurístico nos 31 dias reais, calcula
  economia e dependência da rede, e identifica os cenários de destaque.
- **`visualization.py`** / **`dashboard.py`** — geração de gráficos e a
  interface final.

## Ponto de entrada

[`main.py`](execucao.md) encadeia carga de dados → treino → avaliação →
visualização → dashboard.
