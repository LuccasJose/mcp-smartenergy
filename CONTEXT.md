# SmartEnergy MAS — Contexto do Projeto

## Objetivo

Sistema Multi-Agentes (MAS) com **Q-Learning Cooperativo (IQL)** para minimizar custos energéticos de uma fazenda de grãos. Desenvolvido como **TCC** com dados reais da **Fazenda Buritis** (Luziânia, GO) referentes a **Janeiro de 2025**.

## Domínio

A fazenda possui geração distribuída (solar + eólica), bateria de 24 kWh e quatro cargas: pivô central, bomba de captação, sede administrativa e silo. A tarifa é do tipo **Azul** com pico entre 18h–21h (R$ 1,10/kWh vs R$ 0,68/kWh fora-pico).

## Arquitetura Multi-Agentes

Três agentes independentes (cada um com sua Q-table) compartilham o mesmo **reward cooperativo**:

| Agente | Responsabilidade | Ações |
|---|---|---|
| **Armazenamento** | Gestão da bateria | 0=Carregar, 1=Manter, 2=Descarregar |
| **Consumo** | Corte de cargas interruptíveis | 0=Nada, 1=Corta pivô, 2=Corta captação, 3=Corta ambos |
| **Gerente de Carga** | Teto de consumo horário | 0=Conservador (20kW), 1=Moderado (30kW), 2=Liberal (40kW) |

### Espaço de Estados (120 estados discretos)

Tupla `(bucket_hora, bucket_soc, bucket_solar, bucket_tarifa)`:
- `hora // 6` → 4 valores (madrugada / manhã / tarde / noite)
- `soc // 20` → 5 valores (0–20% / 20–40% / … / 80–100%)
- solar: low (<5kW) / med (5–15kW) / high (>15kW) → 3 valores
- tarifa: normal / pico → 2 valores

### Reward Cooperativo

```
reward = - w_custo * custo_rede
         - pen_soc * (SOC < 15%)
         - pen_teto * (consumo >= teto)
         - pen_producao * (captação cortada)
         + bonus_excedente * kWh_excedente
         + bonus_soc_ok * (30% < SOC < 80%)
```

## Pipeline de Execução (`main.py`)

1. Carrega dados do Excel (31 dias × 24h)
2. Instancia os 3 agentes Q-Learning
3. Treina por 2000 episódios (cada episódio = 1 dia aleatório × 24 timesteps)
4. Gera curvas de aprendizado (reward e custo por episódio)
5. Avalia RL vs heurístico em todos os 31 dias do mês
6. Plota comparativo do dia com maior diferença de custo
7. Analisa 3 cenários: dia mais nublado, mais ensolarado, maior consumo relativo
8. Imprime relatório final com métricas comparativas

## Estrutura de Arquivos

```
src/smarty_energy/
├── config.py        — Hiperparâmetros (alpha, gamma, epsilon, pesos do reward, bateria)
├── data_loader.py   — Leitura do Excel (abas Tarifa, Geracao, Cargas) → DataFrames diários
├── agents.py        — AgenteQL (Q-Learning ε-greedy) + AgentesHeuristicos (baseline com regras)
├── environment.py   — FazendaEnergyEnv (simulador Gym-like: estado → ações → reward)
├── training.py      — Loop IQL: amostra dia, simula 24h, atualiza os 3 agentes, decai ε
├── evaluation.py    — Roda heurístico e RL em dias reais, calcula métricas mensais, identifica cenários
└── visualization.py — Plots: curvas de aprendizado, comparativo dia, cenários (salva em outputs/plots/)
```

## Baseline Heurístico

Agentes baseados em regras com um **índice de estresse financeiro** (0–100) calculado a partir da tarifa atual e nível da bateria. O estresse determina cortes de carga e teto de consumo via limiares fixos (if/else).

## Dados de Entrada

Planilha Excel local (`dados/modelo_gestao_energia_fazenda_v8.xlsx`), com duas
fazendas (`FAZ-001`, `FAZ-002`); a fazenda usada é definida por `ID_FAZENDA` no
`config.py` (padrão `FAZ-002`). Abas relevantes:
- **Tarifa**: curva horária única em R$/kWh (`Fora Ponta` / `Ponta`), 24 valores
- **Geracao**: formato longo — uma linha por gerador (`ID_Gerador`, `Tipo` =
  `Solar FV`/`Eólica`, valor em `Energia_Gerada_kWh`) por fazenda/dia/hora
- **Cargas**: consumo por equipamento nomeado por fazenda/dia/hora

O `data_loader.py` mapeia as 7 cargas da base para as 4 colunas do modelo:
- `pivo_kw` ← `Pivô`
- `captacao_kw` ← `Bomba_Aux`
- `sede_kw` ← `Escritório` + `Cozinha` + `Quarto` (Tipo = `Sede`)
- `silo_kw` ← `Secadora` + `Quadro_Auto` (demais cargas agrícolas)

## Hiperparâmetros Principais (`config.py`)

| Parâmetro | Valor | Descrição |
|---|---|---|
| `n_episodios` | 2000 | Dias simulados no treinamento |
| `alpha` | 0.1 | Taxa de aprendizado |
| `gamma` | 0.95 | Fator de desconto |
| `epsilon` | 1.0 → 0.05 | Exploração (decaimento 0.9975/ep) |
| `bateria_cap_kwh` | 24.0 | Capacidade da bateria |
| `soc_min_pct` | 15% | SOC crítico (penalizado) |
| `eficiencia` | 0.92 | Eficiência de carga da bateria |

## Tecnologias

- Python 3.10+
- NumPy, Pandas, Matplotlib, openpyxl
- Q-Learning tabular (sem deep learning)
