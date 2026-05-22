# SmartEnergy MCP Server

Servidor MCP (Model Context Protocol) para gestão inteligente de energia rural via Q-learning histérico. Otimiza custo tarifário, uso de bateria e corte de cargas em um sistema com geração solar, eólica e conexão à rede elétrica.

---

## Visão geral

O sistema simula e otimiza a operação de uma propriedade rural com:

- Geração solar e eólica com variabilidade climática diária
- Banco de baterias (100 kWh) com eficiência de carga/descarga
- Cargas controláveis: pivô de irrigação, bomba de captação, secador de grãos
- Cargas fixas: sede administrativa, silo
- Conexão à rede com limite de demanda no PCC (65,8 kW)
- Tarifa TOU (Time-of-Use): pico (18h–20h) e fora de pico

O agente aprende a tomar decisões horárias que minimizam o custo em R$ mantendo as restrições físicas do sistema.

---

## Arquitetura

```
mcpsmartenergy/
├── server.py                  # Servidor MCP (FastMCP) — 14 tools expostas
├── config.py                  # Constantes físicas e hiperparâmetros padrão
├── requirements.txt
│
├── environment/
│   ├── energy_env.py          # Simulação horária do sistema energético
│   └── scenarios.py           # Classificação e estatísticas por cenário
│
├── agents/
│   ├── qlearning_agent.py     # AgenteQL — Q-learning histérico (principal)
│   └── baselines.py           # AgenteHeuristico e SemAgente (comparação)
│
└── metrics/
    └── tracker.py             # Rastreamento rigoroso de métricas
```

---

## Ambiente de simulação (`energy_env.py`)

### Resolução temporal
Episódio = 1 dia (24 passos de 1 hora cada).

### Geração renovável
| Fonte | Pico | Variabilidade |
|---|---|---|
| Solar | ~34 kW | Fator climático: ensolarado (1,0), parcial (0,55), nublado (0,18) |
| Eólico | ~10 kW | Fator diário aleatório: 0,4–1,6× |

### Cargas
| Carga | Potência | Controlável | Observações |
|---|---|---|---|
| Pivô de irrigação | 25 kW | Sim (bit 0) | |
| Bomba de captação | 15 kW | Sim (bit 1) | Watchdog: ≥ 6 h/dia |
| Secador de grãos | 20 kW | Sim (bit 2) | |
| Sede administrativa | 3 kW | Não | Sempre ligada |
| Silo | ~4 kW | Não | Variável (0,5–1,5×) |

### Bateria
| Parâmetro | Valor |
|---|---|
| Capacidade | 100 kWh |
| SOC inicial | 50% |
| SOC mínimo | 15% (violação se abaixo) |
| SOC máximo | 95% |
| Potência máxima carga/descarga | 30 kW |
| Eficiência carga/descarga | 95% |

### Tarifa (TOU brasileira)
| Período | Horas | R$/kWh |
|---|---|---|
| Pico | 18h–20h | R$ 0,85 |
| Fora de pico | demais horas | R$ 0,25 |

### Restrições físicas
- **PCC:** importação da rede ≥ 65,8 kW → violação (`pcc_violado = True`)
- **SOC:** bateria < 15% → violação (`soc_violado`)
- **Watchdog:** bomba deve operar ≥ 6 horas por dia; o ambiente força sua ativação nas últimas horas do dia se necessário

### Estado observado pelo agente (`obs`)
```python
{
    "hora": int,               # 0–23
    "soc": float,              # 0–1
    "em_pico_tarifa": bool,
    "geracao_kw": float,       # solar + eólico disponível
    "consumo_base_kw": float,  # carga total sem cortes
}
```

### Info completo por passo (`info`)
```python
# Estado físico
"hora", "soc", "tarifa", "em_pico_tarifa"

# Energético
"geracao_kw", "solar_kw", "eolico_kw", "consumo_kw"
"importacao", "exportacao", "rede_kwh", "excedente"
"bat_carga", "bat_descarga"
"fonte_geracao_kwh", "fonte_bateria_kwh", "fonte_rede_kwh"

# Por máquina
"pivo_kw_consumido", "captacao_kw_consumido"
"sede_kw_consumido", "silo_kw_consumido", "secador_kw_consumido"

# Financeiro
"custo_r", "reward", "tarifa"

# Ações tomadas
"a_arm", "a_cons", "a_ger"

# Violações e flags
"pcc_violado", "bomba_ligada", "bomba_watchdog", "kwh_cortado"
```

---

## Agente Q-learning Histérico (`qlearning_agent.py`)

### Hysteretic Q-learning
O agente usa **duas taxas de aprendizado** distintas:

- **alpha** (otimista): aplicado quando δ ≥ 0 (melhoria)
- **beta** (pessimista, beta << alpha): aplicado quando δ < 0 (degradação)

```
δ = r + γ·max Q(s') - Q(s, a)

Q(s,a) ← Q(s,a) + alpha·δ   se δ ≥ 0
Q(s,a) ← Q(s,a) + beta·δ    se δ < 0
```

Isso estabiliza o aprendizado em ambientes com variabilidade climática não-estacionária (mudança de perfil solar/eólico a cada dia).

### Espaço de estados
5 variáveis discretizadas → **2.160 estados**

| Variável | Buckets |
|---|---|
| hora | 24 (0–23) |
| soc | 5 (0–20%, 20–40%, 40–60%, 60–80%, 80–100%) |
| em_pico_tarifa | 2 (bool) |
| geracao_bucket | 3 (< 8 kW / 8–22 kW / > 22 kW) |
| consumo_bucket | 3 (< 30 kW / 30–55 kW / > 55 kW) |

### Espaço de ações combinado
**72 ações** = `a_arm(3) × a_cons(8) × a_ger(3)`

| Dimensão | Ações | Descrição |
|---|---|---|
| `a_arm` | 3 | 0=carregar bateria, 1=manter, 2=descarregar |
| `a_cons` | 8 | 3 bits: bit0=cortar pivô, bit1=cortar bomba, bit2=cortar secador |
| `a_ger` | 3 | 0=conservador (teto 20 kW), 1=moderado (35 kW), 2=liberal (55 kW) |

### Função de reward
```
reward = -2,0 × custo_r
       - 0,05 × rede_kwh
       - 100,0 × pcc_violado
       - 50,0  × soc_violado
       + 0,03  × (fonte_geracao + fonte_bateria)
```

### Hiperparâmetros padrão
| Parâmetro | Valor | Descrição |
|---|---|---|
| `n_episodios` | 1000 | Episódios de treino |
| `alpha` | 0,10 | LR otimista |
| `gamma` | 0,95 | Fator de desconto |
| `beta` | 0,01 | LR pessimista (hysteretic) |
| `epsilon_inicial` | 1,0 | Exploração máxima |
| `epsilon_final` | 0,05 | Exploração mínima |
| `epsilon_decay` | 0,995 | Decaimento por episódio |

---

## Agentes Baseline (`baselines.py`)

### AgenteHeuristico
Regras fixas para comparação:
- Descarrega bateria durante o pico tarifário
- Carrega bateria fora do pico quando há excedente solar
- Corta pivô e secador durante o pico
- Gerente moderado com geração alta, conservador caso contrário

### SemAgente
Cenário sem sistema de gestão:
- Bateria sempre em manutenção (`a_arm=1`)
- Nenhuma carga cortada (`a_cons=0`)
- Gerente liberal (`a_ger=2`)

---

## Métricas (`tracker.py`)

### Métricas de treinamento (por episódio)
- `rewards_hist` — reward acumulado por episódio
- `custos_hist` — custo R$/dia por episódio
- `epsilons` — ε ao longo do tempo

### Métricas da Q-table (por agente)
- `n_estados` — estados distintos visitados
- `n_updates` — total de atualizações aplicadas
- `epsilon` — taxa de exploração atual

### Métricas de avaliação mensal
| Métrica | Descrição |
|---|---|
| Custo médio diário (R$) | Média de `custo_r` por dia |
| Rede média diária (kWh) | kWh importados da rede/dia |
| Violações SOC (h/dia) | Horas com SOC < 15% por dia |
| Reward médio diário | Média da função objetivo |
| Violações PCC | Horas com importação ≥ 65,8 kW |
| kWh cortado total | Energia não consumida por cortes |

### Métricas por cenário
Todas as métricas de avaliação segmentadas por:
`NUBLADO` / `ENSOLARADO` / `ALTO CONSUMO` / `EQUILIBRADO`

### Dashboard (dados estruturados)
- **Curva de aprendizado:** reward e custo por episódio com média móvel configurável
- **Pico vs fora de pico:** kWh e R$ de pivô, bomba e secador separados por período tarifário
- **Comparação de estratégias:** RL vs Heurístico vs SemAgente com % de redução de custo

---

## Servidor MCP (`server.py`)

### Instalação e execução
```bash
pip install -r requirements.txt
python server.py
# ou
mcp run server.py
```

### Ferramentas disponíveis (14 tools)

#### Configuração
| Tool | Parâmetros | Descrição |
|---|---|---|
| `configure_agent` | n_episodios, alpha, gamma, beta, epsilon_* | Recria o agente com novos hiperparâmetros |

#### Treino
| Tool | Parâmetros | Descrição |
|---|---|---|
| `train_agent` | n_episodios=0 | Treina o agente; retorna sumário do treino |

#### Avaliação
| Tool | Parâmetros | Descrição |
|---|---|---|
| `evaluate_agent` | n_dias=30 | Avalia política greedy; retorna métricas mensais |
| `compare_strategies` | n_dias=30 | RL vs Heurístico vs SemAgente com seed fixo |
| `run_episode` | mode="eval"\|"train" | Trace hora-a-hora completo de 1 episódio |

#### Métricas de treino
| Tool | Descrição |
|---|---|
| `get_training_metrics` | rewards_hist, custos_hist, epsilons + sumário |
| `get_qtable_info` | n_estados, n_updates, epsilon atual, hiperparâmetros |
| `get_learning_curve` | Dados da curva de aprendizado com média móvel |

#### Métricas de avaliação
| Tool | Descrição |
|---|---|
| `get_eval_metrics` | Métricas detalhadas da última avaliação |
| `get_peak_offpeak_stats` | kWh e R$ pico vs fora de pico por carga |
| `get_stats_por_cenario` | Reward e custo médio por cenário climático |

#### Cenários
| Tool | Descrição |
|---|---|
| `identify_scenario` | Cenário do último dia (NUBLADO/ENSOLARADO/ALTO CONSUMO/EQUILIBRADO) |

#### Ambiente
| Tool | Parâmetros | Descrição |
|---|---|---|
| `get_current_state` | — | Estado atual: hora, SOC, tarifa, geração prevista |
| `reset_environment` | reset_agent=False | Reinicia ambiente; opcionalmente zera Q-table |

---

## Dependências

```
mcp >= 1.0.0
numpy >= 1.24.0
```

Python 3.9+ requerido.

---

## Fluxo de uso típico

```
1. configure_agent(alpha=0.1, beta=0.01, gamma=0.95, n_episodios=1000)
2. train_agent()
3. get_training_metrics()        ← verificar convergência
4. get_qtable_info()             ← n_estados e n_updates
5. evaluate_agent(n_dias=30)
6. compare_strategies(n_dias=30) ← RL vs baselines
7. get_peak_offpeak_stats()      ← análise pico/fora-pico
8. get_stats_por_cenario()       ← desempenho por clima
```
