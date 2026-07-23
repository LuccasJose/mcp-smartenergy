---
label: Servidor MCP
icon: server
order: 30
---

# Servidor MCP (IQL)

Servidor MCP (Model Context Protocol) que expõe o sistema multi-agente como
~25 ferramentas para um LLM-juiz treinar, avaliar e auditar a política aprendida.

O MCP é o **intermediador obrigatório** desse modo de uso: o processo do
servidor é o único que detém o dataset, as Q-tables e o tracker de métricas.
O dashboard Streamlit (`src/smarty_energy/mcp/dashboard/`) é um cliente MCP
que se conecta via HTTP e só renderiza payloads retornados pelas tools —
nenhuma métrica é calculada nele.

!!!info Uma física só
Desde a junção dos repositórios, o servidor **importa** o motor do pacote
(`smarty_energy.environment`, `smarty_energy.agents`, `smarty_energy.config`,
`smarty_energy.data_loader`) em vez de manter uma cópia. Qualquer mudança de
física, reward ou dados vale para o pipeline offline e para o MCP ao mesmo
tempo — e os dois produzem exatamente os mesmos números.
!!!

Veja [Execução do MCP](execucao-mcp.md) para o passo a passo de instalação e
inicialização.

---

## Visão geral

O sistema reproduz a operação horária da fazenda real (FAZ-002):

- **Geração**: solar + eólica (inversor FV ≤ 50 kW, eólico ≤ 10 kW nominal)
- **Bateria**: 24 kWh, η carga 0.92 / descarga 0.95, throughput máximo 48 kWh/dia
- **Cargas controláveis**: pivô (lock de 8h/dia, 8 kW), bomba (cronograma fixo 8h/dia, 17,6 kW), secador (meta 20 kWh/dia, teto 2,4 kW)
- **Cargas fixas**: sede (clamp ±20%), silo
- **Conexão à rede**: PCC ≤ 65,8 kW
- **Tarifa TOU**: ~R$0,68 fora-pico / R$1,10 pico (18-20h)

A arquitetura é **IQL (Independent Q-Learning)** com **3 agentes** —
armazenamento, consumo, gerente — todos recebendo o **mesmo reward
cooperativo** do ambiente. O SOC propaga entre episódios.

Detalhes de estado, ações, restrições HARD e reward estão em
[Arquitetura](arquitetura.md) — a fonte é a mesma para os dois modos de uso.

---

## Arquitetura da camada

```text
src/smarty_energy/mcp/
├── server.py          # ~25 tools (FastMCP) — importa o motor do pacote
├── tracker.py         # MetricsTracker: passos/episódios, violações por hora
└── dashboard/         # UI Streamlit — CLIENTE MCP
    ├── app.py         # entry — sidebar conecta ao servidor
    ├── mcp_client.py  # cliente MCP síncrono (streamable-http)
    ├── state.py       # wrappers de tool call usados pelas páginas
    └── pages/
        ├── 1_Overview.py             # health_report em cards
        ├── 2_Curva_de_Aprendizado.py # get_learning_curve + get_td_error_series
        └── 3_Trace_Diario.py         # run_episode + get_hourly_violations

server.py (raiz)       # entry: python server.py [--stdio]
tests/mcp/             # 47 testes (sem rede)
```

---

## Ferramentas

### Configuração
| Tool | Parâmetros | Descrição |
|---|---|---|
| `configure_agents` | hiperparâmetros opcionais | Atualiza α/β/γ/ε e o nº de episódios dos 3 agentes (sem destruir Q-tables) |
| `configure_reward_weights` | 15 pesos opcionais (`w_*`, `pen_*`, `bonus_*`) | Ajusta a função de reward em runtime. Pesos omitidos preservam o valor atual. Restrições físicas (PCC, SOC, capacidade de bateria) permanecem imutáveis. **Após mudar pesos, retreine** — Q-tables existentes ficam parcialmente obsoletas. |

### Treino e avaliação
| Tool | Parâmetros | Descrição |
|---|---|---|
| `train_agents` | n_episodios=0 | Loop IQL com SOC propagando entre dias (mesmo laço do pipeline, com early stopping) |
| `evaluate_agents` | n_dias=30, propagar_soc=True | Greedy sobre o dataset |
| `compare_strategies` | n_dias=30, propagar_soc=True | IQL vs Heurístico vs SemAgente |
| `run_episode` | mode="eval", dia_idx=None | Trace hora-a-hora de 1 dia |

O decaimento de ε é reescalado automaticamente para o horizonte pedido
(`config.ajustar_decay`): sem isso, um treino de 1.000 episódios herdaria o
decay calibrado para 100.000 e os agentes ficariam quase aleatórios.

### Métricas
| Tool | Parâmetros | Descrição |
|---|---|---|
| `get_training_metrics` | — | Sumário do treino + info dos 3 agentes |
| `get_qtables_info` | — | Estatísticas detalhadas das 3 Q-tables |
| `get_td_error_series` | agente="armazenamento" | Série de TD-error (até 5000 pontos) de 1 agente |
| `get_learning_curve` | janela_media_movel=20 | Reward, custo e epsilon por episódio |
| `get_eval_metrics` | agente="iql_eval" | Métricas da última avaliação |
| `get_peak_offpeak_stats` | agente="iql_eval" | kWh e R$ pico vs fora-pico |
| `get_stats_por_cenario` | agente="iql_eval" | Reward/custo médio por cenário |
| `get_hourly_violations` | agente="iql_eval" | Violações SOC/PCC/teto por hora-do-dia |

### Cenários e dataset
| Tool | Parâmetros | Descrição |
|---|---|---|
| `identify_scenarios` | — | Índices dos 3 dias extremos (nublado/ensolarado/alto_consumo) |
| `get_dataset_info` | — | Fazenda, n_dias, range de datas, tarifa horária |
| `select_day` | dia_idx | Troca o dia "atual" para get_current_state / step |

### Ambiente
| Tool | Parâmetros | Descrição |
|---|---|---|
| `get_current_state` | — | Estado atual do env (dia selecionado, hora) |
| `reset_environment` | reset_agents=False, dia_idx=None | Reinicia env (e opcionalmente Q-tables) |

### Integração com agente externo
| Tool | Parâmetros | Descrição |
|---|---|---|
| `get_observation` | — | Obs + estado discretizado |
| `step_environment` | a_arm, a_cons, a_ger | 1 passo no env (obs, reward, done, info) |
| `get_actions` | explore=False | Ações dos 3 agentes IQL + Q-values top-3 |
| `save_qtables` | dir_path="", label="" | Salva um **run versionado** em `outputs/runs/` (ou 3 pickles soltos se `dir_path`) |
| `load_qtables` | dir_path="", run_id="" | Carrega o run mais recente, um run específico, ou pickles soltos |
| `get_financeiro_state` | — | Saldo de créditos + estresse + tarifa atual |

!!!success Runs compartilhados
`save_qtables` / `load_qtables` usam o mesmo `outputs/runs/` do pipeline
offline. Um treino longo feito com `python main.py` pode ser carregado pelo
servidor, e um treino disparado pelo LLM aparece em `main.py --replot` e nos
dashboards.
!!!

### Diagnóstico para LLM-as-a-judge
| Tool | Descrição |
|---|---|
| `health_report` | Payload consolidado: cobertura/TD-error dos 3 agentes, sumário do treino, comparação com baselines, `pesos_reward_modificados` e alertas heurísticos |
| `describe_schema` | Esquema completo: estado, ações, restrições HARD, reward, tarifa |

---

## Fluxo de uso típico

```
1. get_dataset_info()                 ← entender o dataset
2. describe_schema()                  ← entender estado/ações/reward
3. configure_agents(n_episodios=5000)
4. train_agents()
5. evaluate_agents(n_dias=31)
6. compare_strategies(n_dias=31)
7. health_report()                    ← veredito consolidado
8. get_hourly_violations(...)         ← se houver violações
9. identify_scenarios()               ← análise por dia extremo
10. run_episode(dia_idx=...)          ← trace detalhado
```

## Loop LLM-as-a-judge (autônomo)

Com `configure_reward_weights`, o cliente LLM pode rodar um ciclo fechado de
auto-ajuste — diagnosticar → decidir → agir → reavaliar:

```
health_report()                       ← lê veredito atual
    ↓
decisão do LLM
    ├─ "treinar mais" ──────────► train_agents(n_episodios=N)
    ├─ "aprovar"     ──────────► fim
    └─ "ajustar pesos" ────────► configure_reward_weights(pen_pcc=25, ...)
                                  └─► reset_environment(reset_agents=True)
                                  └─► train_agents()
    ↓
evaluate_agents() + health_report()   ← reavaliação
    ↓
(repete até aprovar)
```

---

## Dashboard Streamlit (cliente MCP)

Requer o servidor rodando à parte:

```powershell
# terminal 1 — servidor MCP (fica rodando)
python server.py

# terminal 2 — dashboard
python -m streamlit run src/smarty_energy/mcp/dashboard/app.py
```

| Página | Tools usadas | O que mostra |
|---|---|---|
| **Overview** | `health_report`, `get_dataset_info` | Veredito consolidado: cobertura/TD-error dos 3 agentes, comparação com baselines, alertas |
| **Curva de Aprendizado** | `get_learning_curve`, `get_td_error_series` | Reward/custo/epsilon por episódio com média móvel + TD-error rolante |
| **Trace Diário** | `run_episode`, `select_day`, `identify_scenarios`, `get_hourly_violations`, `describe_schema` | Um dia hora-a-hora (geração/consumo/SOC/custo) + heatmap de violações |

A sidebar concentra conexão ao MCP, treino (slider de episódios) e avaliação
(`evaluate_agents` / `compare_strategies`, com toggle de propagação de SOC).

---

## Testes

```bash
python -m pytest tests/mcp -v
```

47 testes cobrindo invariantes físicos do env (PCC, SOC, throughput,
schedules HARD), hysteretic Q-learning, baselines, tracker e tools do
servidor. Usam fixtures sintéticas, **sem download** da base.

---

## Transporte

Por padrão o servidor sobe em **streamable-http** (`127.0.0.1:8000`,
configurável por `MCP_HOST`/`MCP_PORT`), como processo único e de longa
duração compartilhado pelo dashboard e por clientes MCP.

```bash
python server.py --stdio      # modo clássico de subprocesso stdio
```

Variáveis de ambiente úteis: `MCP_N_EPISODIOS` (episódios por chamada de
`train_agents`, default 1000), `SHEET_ID` e `ID_FAZENDA` (fonte de dados).
