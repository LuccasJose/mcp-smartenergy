# SmartEnergy MCP Server (IQL)

Servidor MCP (Model Context Protocol) que espelha o projeto **Smart_Energy** —
sistema multi-agente com Q-Learning cooperativo para gestão energética de
fazenda de grãos. Expõe ~25 ferramentas para um LLM-juiz treinar, avaliar
e auditar a política aprendida.

O MCP é o **intermediador obrigatório** de todo o sistema: `server.py` é o
único processo que detém o dataset, as Q-tables e o tracker de métricas.
O dashboard Streamlit (`dashboard/`) **não** importa mais `agents/`,
`environment/` ou `metrics/` diretamente — ele é um cliente MCP que se
conecta ao servidor via HTTP e só renderiza payloads retornados pelas
tools. Não há caminho de treino, avaliação ou leitura de métrica que
não passe pelo MCP. Veja o [MANUAL.md](MANUAL.md) para o passo a passo
de instalação e inicialização.

---

## Visão geral

O sistema reproduz a operação horária de uma fazenda real (FAZ-002), com
dados baixados de planilha pública no Google Sheets:

- **Geração**: solar + eólica (inversor FV ≤ 50 kW, eólico ≤ 10 kW nominal)
- **Bateria**: 24 kWh, η carga 0.92 / descarga 0.95, throughput máximo 48 kWh/dia
- **Cargas controláveis**: pivô (lock de 8h/dia), bomba (cronograma fixo 8h/dia), secador (meta 20 kWh/dia)
- **Cargas fixas**: sede (clamp ±20%), silo
- **Conexão à rede**: PCC ≤ 65.8 kW
- **Tarifa TOU**: ~R$0.68 fora-pico / R$1.10 pico (18-20h)

A arquitetura é **IQL (Independent Q-Learning)** com **3 agentes** —
armazenamento, consumo, gerente — todos recebendo o **mesmo reward
cooperativo** do ambiente. SOC propaga entre episódios.

---

## Arquitetura

```
MCP_SmartEnergy/
├── server.py                  # Servidor MCP (FastMCP) — ~24 tools
├── config.py                  # CONFIG, TETOS_KW, BOMBA_HORAS_ON
├── requirements.txt
│
├── environment/
│   ├── data_loader.py         # Baixa Sheets via urllib (1 vez no startup)
│   ├── energy_env.py          # FazendaEnergyEnv (porte do Smart_Energy)
│   └── scenarios.py           # Cenários ex-post (nublado/ensolarado/alto_consumo)
│
├── agents/
│   ├── qlearning_agent.py     # AgenteQL + IQLSystem (orquestra os 3)
│   ├── baselines.py           # AgentesHeuristicos, SemAgente
│   └── financeiro.py          # AgenteFinanceiro (estresse + créditos)
│
├── metrics/
│   └── tracker.py             # Tracker com violações por hora
│
├── dashboard/                  # UI Streamlit — CLIENTE MCP (não é opcional)
│   ├── app.py                  # Entry — sidebar conecta ao servidor MCP
│   ├── mcp_client.py           # Cliente MCP síncrono (streamable-http)
│   ├── state.py                 # Wrappers de tool call para uso nas páginas
│   └── pages/
│       ├── 1_Overview.py              # health_report() em cards
│       ├── 2_Curva_de_Aprendizado.py  # get_learning_curve + get_td_error_series
│       └── 3_Trace_Diario.py          # run_episode + get_hourly_violations
│
└── tests/                     # 47 testes pytest (sem rede)
    ├── conftest.py            # Fixtures sintéticas (dia + tarifa)
    ├── test_env.py            # PCC, SOC, throughput, schedules, reward
    ├── test_agent.py          # Hysteretic, save/load, IQL
    ├── test_baselines.py      # Heurístico + SemAgente
    ├── test_tracker.py        # Hourly, peak/offpeak, eval
    └── test_tools.py          # configure_*, compare, health_report
```

---

## Ambiente (`FazendaEnergyEnv`)

### Estado discreto (2.160 estados)

| Variável | Buckets |
|---|---|
| hora    | 4 (0-5h / 6-11h / 12-17h / 18-23h) |
| soc     | 10 (a cada 10%) |
| solar   | 3 (<5 kW / 5-15 / >15) |
| stress  | 3 (<30 / 30-70 / >70 — calculado pelo AgenteFinanceiro) |
| meta_sec | 2 (secador atingiu 20 kWh diários?) |
| bomba   | 3 (<3h / 3-5h / ≥6h operadas) |

### Espaço de ações

Os 3 agentes IQL têm espaços independentes:

| Agente | Ações | Descrição |
|---|---|---|
| armazenamento | 3 | 0=carregar, 1=manter, 2=descarregar |
| consumo       | 8 | bitmask 3 bits — bit0=cortar pivô, bit1=cortar bomba, bit2=cortar secador |
| gerente       | 3 | 0=conservador (20 kW), 1=moderado (30 kW), 2=liberal (40 kW) |

### Restrições HARD implementadas

- **R-PIVO**: 8h consecutivas + apenas 1 ativação/dia (lock automático override a ação do agente quando ativo)
- **R-BOMBA**: cronograma fixo nas horas `{0,1,6,7,12,13,21,22}` — ação do agente é **ignorada**
- **R-SECADOR**: meta diária 20 kWh; rescue tardio força ON em 2.2 kW se faltar energia
- **R-SEDE**: clamp em ±20% do ideal; eco-mode (−20%) em stress > 80
- **R-PCC**: importação/exportação ≤ 65.8 kW
- **R-BAT**: throughput diário ≤ 48 kWh

### Reward cooperativo

```
reward = - 8.0 * custo_r                           # economia tarifária (sinal dominante)
         - 0.5 * (stress / 10)                     # estresse financeiro
         - 12.0 * soc_critico
         - 8.0  * teto_excedido
         - 10.0 * pcc_violado
         - 5.0  * kwh_cortado                      # produção perdida
         - pen_secador_meta (20.0 se não atingiu)
         - pen_pivo_pico (18.0 se pivô em pico)
         - pen_secador_pico (8.0 se secador em pico)
         + bonus_pivo_solar (3.0 com sol ≥ 15kW)
         + bonus_sec_excedente (2.0 com excedente ≥ 5kW)
         + 1.2 * bat_carga (se carregando com excedente)
         + 0.5 * excedente * tarifa
         + 1.0 * (30 < soc < 80)
```

---

## Dataset

Baixado uma vez no startup do servidor via `urllib.request.urlopen`:

- **Planilha**: `SHEET_ID=1sjs2XLNEZp2oPxm_YLwsX9DxPxIfks32` (sobrescrevível via env var)
- **Fazenda**: `ID_FAZENDA=FAZ-002` (também sobrescrevível)
- **Período**: 31 dias de janeiro/2025
- **Abas usadas**: `Geracao`, `Cargas`, `Tarifa`
- **Mapeamento** (base nova → modelo):
  - `pivo_kw` ← `Pivô`
  - `captacao_kw` ← `Bomba_Aux`
  - `sede_kw` ← cargas `Tipo="Sede"` (Escritório + Cozinha + Quarto)
  - `silo_kw` ← `Secadora + Quadro_Auto`

---

## Ferramentas MCP

### Configuração
| Tool | Parâmetros | Descrição |
|---|---|---|
| `configure_agents` | hiperparâmetros opcionais | Atualiza α/β/γ/ε dos 3 agentes (sem destruir Q-tables) |
| `configure_reward_weights` | 15 pesos opcionais (`w_*`, `pen_*`, `bonus_*`) | Ajusta a função de reward em runtime. Pesos omitidos preservam o valor atual. Restrições físicas (PCC, SOC, capacidade de bateria) permanecem imutáveis. **Após mudar pesos, retreine** — Q-tables existentes ficam parcialmente obsoletas. |

### Treino e avaliação
| Tool | Parâmetros | Descrição |
|---|---|---|
| `train_agents` | n_episodios=0 | Loop IQL com SOC propagando entre dias |
| `evaluate_agents` | n_dias=30, propagar_soc=True | Greedy sobre o dataset |
| `compare_strategies` | n_dias=30, propagar_soc=True | IQL vs Heurístico vs SemAgente |
| `run_episode` | mode="eval", dia_idx=None | Trace hora-a-hora de 1 dia |

### Métricas
| Tool | Parâmetros | Descrição |
|---|---|---|
| `get_training_metrics` | — | Sumário do treino + info dos 3 agentes |
| `get_qtables_info` | — | Estatísticas detalhadas das 3 Q-tables |
| `get_td_error_series` | agente="armazenamento" | Série completa de TD-error (até 5000 pontos) de 1 agente — usado pelo dashboard para plotar convergência |
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
| `save_qtables` | dir_path="qtables" | Salva as 3 Q-tables em pickle |
| `load_qtables` | dir_path="qtables" | Carrega Q-tables salvas |
| `get_financeiro_state` | — | Saldo de créditos + estresse + tarifa atual |

### Diagnóstico para LLM-as-a-judge
| Tool | Descrição |
|---|---|
| `health_report` | Payload consolidado: cobertura/TD-error dos 3 agentes, sumário treino, comparação com baselines, `pesos_reward_modificados` (quando aplicável) e alertas heurísticos |
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
10. run_episode(dia_idx=...)           ← trace detalhado
```

## Loop LLM-as-a-judge (autônomo)

Com `configure_reward_weights`, o cliente LLM pode rodar um ciclo
fechado de auto-ajuste — diagnosticar → decidir → agir → reavaliar:

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

UI interativa que se conecta ao servidor MCP via HTTP (`dashboard/mcp_client.py`)
— **não** importa `agents/`, `environment/` ou `metrics/` diretamente.
Toda métrica exibida vem de uma tool call. Requer o servidor rodando à parte.

> **Antes de colar os comandos abaixo**: eles assumem que você já está
> dentro da pasta `mcp-smartenergy/` (a raiz do projeto, onde ficam
> `server.py` e `dashboard/`) e que já instalou as dependências num
> ambiente virtual — veja [MANUAL.md](MANUAL.md). Rodar
> `pip install` ou `streamlit run` fora dessa pasta, ou no Python global
> em vez do venv, é a causa mais comum de erro aqui.

```powershell
# terminal 1 — servidor MCP (fica rodando)
cd caminho\para\mcp-smartenergy
.venv\Scripts\python.exe server.py

# terminal 2 — dashboard (conecta no servidor acima)
cd caminho\para\mcp-smartenergy
.venv\Scripts\python.exe -m streamlit run dashboard\app.py
```

```bash
# Linux/Mac — mesma ideia, com o venv ativado
cd caminho/para/mcp-smartenergy && source .venv/bin/activate

# terminal 1
python server.py

# terminal 2
python -m streamlit run dashboard/app.py
```

3 páginas, todas construídas a partir de tool calls:

| Página | Tools usadas | O que mostra |
|---|---|---|
| **Overview** | `health_report`, `get_dataset_info` | Veredito consolidado: cobertura/TD-error dos 3 agentes, comparação com baselines, alertas heurísticos |
| **Curva de Aprendizado** | `get_learning_curve`, `get_td_error_series` | Reward/custo/epsilon por episódio com média móvel + TD-error rolante dos 3 agentes |
| **Trace Diário** | `run_episode`, `select_day`, `identify_scenarios`, `get_hourly_violations`, `describe_schema` | Roda 1 dia (greedy/exploração), geração/consumo/SOC/custo hora-a-hora + heatmap de violações |

A sidebar concentra conexão ao MCP, treino (slider de episódios,
`configure_agents` + `train_agents`) e avaliação (`evaluate_agents` /
`compare_strategies`, com toggle de propagação de SOC).

---

## Testes

Dentro da pasta `mcp-smartenergy/`, com o venv ativado (`pytest` já está
em `requirements.txt`):

```bash
python -m pytest tests/ -v
```

47 testes cobrindo invariantes físicos do env (PCC, SOC, throughput,
schedules HARD), hysteretic Q-learning, baselines, tracker e tools do
servidor. Testes usam fixtures sintéticas, **sem download** do Sheets.

---

## Dependências

```
mcp >= 1.9.0        # server.py e dashboard/mcp_client.py (streamable-http)
numpy >= 1.24.0
pandas >= 2.0
openpyxl >= 3.1

streamlit >= 1.30   # dashboard (cliente MCP, não é mais opcional se for usá-lo)
plotly >= 5.18      # dashboard
pytest >= 8.0       # opcional (testes)
```

Python 3.10+ requerido (sintaxe `int | None`). Conexão à internet requerida no
startup do **servidor** para baixar a planilha (~1 MB) — o dashboard não
baixa nada, só conversa com o servidor.
