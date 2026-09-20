# SmartEnergy MAS — Contexto do Projeto

## Objetivo

Sistema Multi-Agentes (MAS) com **Q-Learning Cooperativo (Hysteretic IQL)** para
minimizar custos energéticos de uma fazenda de grãos. Desenvolvido como **TCC**
com dados reais da **Fazenda Buritis** (Luziânia, GO) referentes a **Janeiro de 2025**.

Este repositório é a junção de dois projetos que evoluíram em paralelo — o motor
de RL (`Smart_Energy`, de YuriRes) e a camada MCP (`mcp-smartenergy`, de
LuccasJose) — com os dois históricos Git preservados. A camada MCP hoje
**importa** o motor do pacote em vez de manter um fork: há uma só física, uma só
config e um só loader.

## Domínio

A fazenda possui geração distribuída (solar + eólica), bateria de 24 kWh e cinco
cargas: pivô central, bomba de captação, secador, sede administrativa e silo.
A tarifa é do tipo **Azul** com pico entre 18h–21h (R$ 1,10/kWh vs R$ 0,68/kWh
fora-pico). Conexão à rede limitada a 65,8 kW (PCC).

## Arquitetura Multi-Agentes

Três agentes independentes (cada um com sua Q-table) compartilham o mesmo
**reward cooperativo**:

| Agente | Responsabilidade | Ações |
|---|---|---|
| **Armazenamento** | Gestão da bateria | 0=Excedente, 1=Manter, 2/3/4=Descarregar 25/50/100% do déficit, 5=Excedente e rede elegível |
| **Consumo** | Início do ciclo do pivô | bitmask 3 bits (0–7): bit 1 participa do início do pivô; bits 2 e 4 são ignorados por bomba e secador |
| **Gerente de Carga** | Teto de consumo horário | 0=Conservador (20kW), 1=Moderado (30kW), 2=Liberal (40kW) |

### Espaço de Estados (3780 estados discretos)

Tupla `(bucket_hora, bucket_soc, bucket_solar, bucket_stress, meta_sec, bucket_bomba)`:
- período energético → 7 valores: 0-5h / 6-11h / 12-15h / 16-17h / 18-19h / 20h / 21-23h
- `soc // 10` → 10 valores
- solar: low (<5kW) / med (5 ≤ solar < 15kW) / high (≥15kW) → 3 valores
- stress: <30 / 30 ≤ stress < 70 / ≥70 (índice do AgenteFinanceiro) → 3 valores
- meta do secador atingida (20 kWh/dia) → 2 valores
- horas de bomba operadas: <3 / 3–5 / ≥6 → 3 valores

### Restrições HARD (aplicadas pelo ambiente)

- **R-PIVO**: 8h consecutivas, 1 ativação/dia, 8 kW durante o lock
- **R-BOMBA**: cronograma fixo nas horas {3,4,9,10,15,16,21,22} a 17,6 kW — ação do agente ignorada
- **R-SECADOR**: potência horária da base, bit de corte ignorado; meta diária 20 kWh com penalidade terminal, sem rescue ativo
- **R-SEDE**: clamp em ±20% do ideal; eco-mode (−20%) com stress ≥ 70
- **R-PCC**: importação/exportação ≤ 65,8 kW, mutuamente exclusivas
- **R-BAT**: throughput diário compartilhado ≤ 30 kWh DC, η carga 0,92 / descarga 0,95

Contratos do piloto conferidos em 20/09/2026: [visão técnica](docs/arquitetura.md),
[regras de domínio](docs/regras-dominio.md) e [plano/rastreabilidade](docs/reorganizacao.md).
Os demais contratos e a fundamentação científica dos parâmetros continuam em revisão.

### Reward Cooperativo

Resumo conceitual, não exaustivo: termos econômicos, reserva e offset atuais
devem ser conferidos em `FazendaEnergyEnv.step` antes de reproduzir resultados.

```
reward = - w_custo * custo_rede
         - w_estresse * (stress / 10)
         - pen_soc * (SOC < 15%)
         - pen_teto * (consumo >= teto)
         - pen_pcc * (PCC violado)
         - pen_producao * kWh_cortado
         - pen_secador_meta / pen_pivo_pico / pen_secador_pico
         + bonus_pivo_solar + bonus_sec_excedente
         + w_bonus_carga * kWh carregados com excedente
         + bonus_excedente * kWh_excedente * tarifa
         + bonus_soc_ok * (30% < SOC < 80%)
         + bonus_descarga_pico * kWh AC descarregados no pico
```

## Dois modos de uso

### Pipeline offline (`main.py`)

1. Carrega os dias de FEMS ou base v8 (24h por dia; padrão de janeiro: 31 dias)
2. Instancia os 3 agentes Q-Learning
3. Treina (cada episódio = 1 dia × 24 timesteps, SOC propagando entre dias),
  executando o horizonte configurado e restaurando o melhor checkpoint greedy disponível
4. Versiona o treino em `outputs/runs/<run_id>/`
5. Avalia sem-agente / heurístico / RL nos dias carregados
6. Gera curvas, comparativo do dia de maior diferença e os 3 cenários
7. Abre o dashboard (Tkinter ou Dash com `--web`)

### Servidor MCP (`server.py`)

Expõe 45 ferramentas registradas para um LLM-juiz treinar, avaliar e auditar a política
(loop `health_report` → decidir → `configure_reward_weights`/`train_agents` →
reavaliar). O dashboard Streamlit é um cliente puro dessas ferramentas.
`save_qtables`/`load_qtables` usam o mesmo `outputs/runs/` do pipeline.

O dashboard oferece tambem [cinco divisoes selecionaveis](docs/divisoes-dataset.md)
em fluxo isolado: previa, treino/validacao e teste final explicito. Esse protocolo
nao substitui a politica ativa nem altera os runs legados.

## Estrutura de Arquivos

```
src/smarty_energy/
├── config.py        — Hiperparâmetros, pesos do reward, limites, ajustar_decay
├── data_loader.py   — FEMS ou base v8 (Sheets/Excel) → DataFrames diários + metadados
├── agents.py        — AgenteQL, IQLSystem, heurístico, sem-agente, financeiro
├── environment.py   — FazendaEnergyEnv (estado → ações → reward)
├── training.py      — Loop IQL com seleção de checkpoint greedy (aceita tracker do MCP)
├── evaluation.py    — Execução por dia, métricas mensais, cenários
├── metrics.py       — Métricas primárias do plano de testes (4.1/4.2)
├── runs.py          — Versionamento de treinos
├── benchmark.py     — RL × LLM (Wilcoxon pareado, custo operacional)
├── llm_policy.py    — Política de controle por LLM (tool-use)
├── visualization.py — Figuras
├── dashboard*.py    — Dashboards Tkinter e Dash
└── mcp/             — server.py (tools), state.py, tracker.py, dashboard/ (Streamlit)
```

## Baseline Heurístico

Agentes baseados em regras com um **índice de estresse financeiro** (0–100)
calculado a partir da tarifa atual e nível da bateria. O estresse determina
cortes de carga e teto de consumo via limiares fixos (if/else). O baseline
**Sem Agente** (bateria em manter, pivô iniciado às 16h, teto liberal) é a
referência C0 implementada, não uma comprovação da operação real da fazenda.

## Dados de Entrada

Base v8 com duas fazendas (`FAZ-001`, `FAZ-002`); a usada é definida por
`ID_FAZENDA` (padrão `FAZ-002`). FEMS Parquet tem prioridade quando
`FEMS_DATASET_DIR` está configurado; depois Google Sheets quando `SHEET_ID`
está definido no `.env`, senão o Excel local
(`dados/modelo_gestao_energia_fazenda_v8.xlsx`). Abas relevantes:
- **Tarifa**: curva horária única em R$/kWh (`Fora Ponta` / `Ponta`), 24 valores
- **Geracao**: formato longo — uma linha por gerador (`ID_Gerador`, `Tipo` =
  `Solar FV`/`Eólica`, valor em `Energia_Gerada_kWh`) por fazenda/dia/hora
- **Cargas**: consumo por equipamento nomeado por fazenda/dia/hora

Mapeamento das cargas da base para as colunas do modelo:
- `pivo_kw` ← `Pivô`
- `captacao_kw` ← `Bomba_Aux`
- `sede_kw` ← `Escritório` + `Cozinha` + `Quarto` (Tipo = `Sede`)
- `secador_kw` ← `Secadora` (potência da base, bit de corte ignorado)
- `silo_kw` ← `Quadro_Auto` (fundo fixo)

## Hiperparâmetros Principais (`config.py`)

| Parâmetro | Valor | Descrição |
|---|---|---|
| `n_episodios` | 100000 | Dias simulados no treino do pipeline (cap contra drift) |
| `alpha` / `beta` | 0.1 / 0.01 | Taxas otimista e pessimista (Hysteretic) |
| `gamma` | 0.98 | Fator de desconto |
| `epsilon` | 1.0 → 0.01 | Exploração (decay 0.99993/ep; reescalado em treinos curtos) |
| `bateria_cap_kwh` | 24.0 | Capacidade da bateria |
| `soc_min_pct` | 15% | SOC crítico (penalizado) |
| `eficiencia_carga` | 0.92 | Eficiência de carga da bateria |

## Tecnologias

- Python 3.10+
- NumPy, Pandas, Matplotlib, openpyxl, python-dotenv
- Dash/Plotly (dashboard web), Streamlit (dashboard MCP)
- SDK `mcp` (servidor de ferramentas)
- Q-Learning tabular (sem deep learning)
