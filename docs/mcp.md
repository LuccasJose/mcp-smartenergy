---
label: Servidor MCP
icon: server
order: 30
---

# Servidor MCP (IQL)

Servidor MCP (Model Context Protocol) que expõe o sistema multi-agente como
45 ferramentas registradas para um LLM-juiz treinar, avaliar e auditar a política aprendida.

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
tempo. A paridade é verificada em cenários sintéticos com os mesmos dados,
configuração e protocolo de SoC; não se presume igualdade para runs distintos.
!!!

Veja [Execução do MCP](execucao-mcp.md) para o passo a passo de instalação e
inicialização.

---

## Visão geral

O sistema reproduz a operação horária da fazenda real (FAZ-002):

- **Geração**: solar + eólica (inversor FV ≤ 50 kW, eólico ≤ 10 kW nominal)
- **Bateria**: 24 kWh, η carga 0.92 / descarga 0.95, throughput compartilhado máximo 30 kWh DC/dia
- **Cargas operacionais**: pivô (início escolhido sob restrições, lock de 8h/dia, 8 kW), bomba (cronograma fixo 8h/dia, 17,6 kW), secador (potência da base, meta 20 kWh/dia)
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
├── server.py          # 45 tools (FastMCP) — importa o motor do pacote
├── state.py           # ServerState — estado operacional do processo
├── tracker.py         # MetricsTracker: passos/episódios, violações por hora
└── dashboard/         # UI Streamlit — CLIENTE MCP
    ├── app.py         # entry — sidebar conecta ao servidor
    ├── mcp_client.py  # cliente MCP síncrono (streamable-http)
    ├── state.py       # wrappers de tool call usados pelas páginas
    └── pages/
        ├── 1_Executar_Analise.py
        ├── 2_Visao_Geral.py
        ├── 3_Curva_de_Aprendizado.py
        ├── 4_Trace_Diario.py
        ├── 5_Equipamentos.py
        ├── 6_LLM_Juiz.py
        ├── 7_Fazendas_FEMS.py
        └── 8_Divisoes_Dataset.py

server.py (raiz)       # entry: python server.py [--stdio]
tests/mcp/             # testes de integração e contratos
```

---

## Ferramentas

As tabelas resumem as operações principais; `list_tools` do protocolo fornece
o catálogo registrado completo, incluindo schemas de argumentos.

### Configuração
| Tool | Parâmetros | Descrição |
|---|---|---|
| `configure_agents` | hiperparâmetros opcionais | Atualiza α/β/γ/ε e o nº de episódios dos 3 agentes (sem destruir Q-tables) |
| `configure_reward_weights` | pesos opcionais (`w_*`, `pen_*`, `bonus_*`) | Ajusta a função de reward em runtime. Pesos omitidos preservam o valor atual. Restrições físicas (PCC, SOC, capacidade de bateria) permanecem imutáveis. **Após mudar pesos, retreine** — Q-tables existentes ficam parcialmente obsoletas. |

### Treino e avaliação
| Tool | Parâmetros | Descrição |
|---|---|---|
| `train_agents` | n_episodios=0 | Loop IQL com SOC propagando entre dias; mesmo laço do pipeline, com seleção de checkpoint greedy e sem parada antecipada |
| `evaluate_agents` | n_dias=30, propagar_soc=True | Greedy sobre o dataset |
| `compare_strategies` | n_dias=30, propagar_soc=True | IQL vs Heurístico vs SemAgente |
| `run_episode` | mode="eval", dia_idx=None | Trace hora-a-hora de 1 dia |

O decaimento de ε é reescalado automaticamente para o horizonte pedido
(`config.ajustar_decay`): sem isso, um treino de 1.000 episódios herdaria o
decay calibrado para 100.000 e os agentes ficariam quase aleatórios.

### Métricas
As ferramentas `plan_dataset_splits`, `get_split_experiment`,
`train_split_experiment` e `evaluate_split_test` oferecem um fluxo isolado de
[divisoes selecionaveis](divisoes-dataset.md), com previa, validacao e teste
final explicito. Nao substituem a politica ativa nem executam o LLM-juiz.

| Tool | Parâmetros | Descrição |
|---|---|---|
| `get_training_metrics` | — | Sumário do treino + info dos 3 agentes |
| `get_qtables_info` | — | Estatísticas detalhadas das 3 Q-tables |
| `get_td_error_series` | agente="armazenamento" | Série de TD-error (até 5000 pontos) de 1 agente |
| `get_learning_curve` | janela_media_movel=20 | Reward, custo e epsilon por episódio |
| `get_eval_metrics` | agente="iql_eval" | Métricas da última avaliação |
| `get_peak_offpeak_stats` | agente="iql_eval" | kWh e R$ pico vs fora-pico |
| `get_battery_dispatch_stats` | agente="iql_eval" | Carga/descarga por tarifa e motivos de bloqueio |
| `get_stats_por_cenario` | agente="iql_eval" | Reward/custo médio por cenário |
| `get_hourly_violations` | agente="iql_eval" | Violações SOC/PCC/teto por hora-do-dia |

### Cenários e dataset
| Tool | Parâmetros | Descrição |
|---|---|---|
| `identify_scenarios` | — | Índices dos 3 dias extremos (nublado/ensolarado/alto_consumo) |
| `get_dataset_info` | — | Fazenda, n_dias, range de datas, tarifa horária |
| `select_day` | dia_idx | Troca o dia "atual" para get_current_state / step |
| `switch_dataset` | dataset_dir, id_fazenda="", mes=1 | Carrega FEMS e reinicia o estado de análise em memória |

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

Use a seleção sintética explícita do [plano de reorganização](reorganizacao.md).
Ela inclui `test_tools`, `test_switch_dataset`, `test_experiments` e
`test_fisica_unificada`, com loader injetado em `initialize`, arquivos
temporários e treinos curtos de dois episódios.
Também inclui test_transport.py (`tests/mcp/test_transport.py`): subprocessos
reais para stdio e HTTP loopback, cliente SDK e cliente Python do dashboard.
Não equivale a executar toda a suíte MCP, todas as tools ou a UI Streamlit.

## Contratos verificados

### R-MCP-002: ciclo de inicialização

Importar `smarty_energy.mcp.server` registra as tools, mas não chama o loader
nem cria dataset, agentes, tracker ou ambiente do servidor. Configurações
continuam sendo importadas, incluindo o comportamento de leitura de ambiente
do módulo config; não é uma garantia de importação totalmente sem efeitos.

`main()` chama `initialize()` antes de `mcp.run`. `initialize(loader=None)`
usa o loader oficial por padrão; um callable sem argumentos pode fornecer
`(dias, tarifa)` nos testes. Metadados e objetos de execução são preparados
localmente antes de publicados. Se a carga ou construção falhar, a exceção
propaga, o transporte não inicia e é possível tentar novamente.

Após sucesso, chamadas repetidas não recarregam dados nem reiniciam estado,
mesmo com outro loader. Para trocar dados de uma sessão ativa, use a tool
`switch_dataset`; não chame initialize como reset. `initialize` é API Python
de startup, não uma tool MCP. Scripts Python devem inicializar antes de usar
funções das tools ou acessar o estado, inclusive antes de `server.mcp.run()`.

Os comandos `python server.py` e `python server.py --stdio` permanecem iguais.
As quatro fixtures de importação foram migradas e os testes verificam startup
com transportes simulados, falha/nova tentativa e idempotência; os testes de
transporte complementam com execução real de `main` após injeção dos dados.
Uma referência
de estado e CONFIG continuam compartilhados por processo: não há isolamento
por cliente, lock de inicialização ou suporte a initialize concorrente.
Veja ADR-002 e ADR-003 no [plano](reorganizacao.md).

### R-MCP-003: representação do estado

ServerState (`src/smarty_energy/mcp/state.py`) reúne dados, tarifa, metadados,
IQL, baselines, tracker, ambiente, dia ativo, traces, snapshots e referências
de run/experimento. É um contêiner dos objetos do motor, sem física ou loader
próprio. O servidor publica apenas `_state` depois da preparação completa.

As tools usam `get_state()`; antes de initialize essa função levanta RuntimeError
com orientação explícita. Ela não é uma tool MCP. Acessos Python como
`server.DIAS`, `server.env` ou `server._snapshots` foram substituídos por
`server.get_state().dias`, `.env` e `.snapshots`, sem aliases antigos.
O objeto retornado é mutável, não uma cópia; clientes normais devem usar as tools.

Reset e troca de dataset atualizam campos do mesmo objeto. Os traces da política
ativa e do snapshot permanecem separados; o snapshot continua sem aprender.
O dicionário de snapshots é criado por instância, mas os componentes passados ao
construtor são referências: instanciar a classe não isola dados, agentes ou CONFIG
automaticamente. A operação ainda é compartilhada por processo e não transacional.

### R-MCP-001: dados e estado de análise

`switch_dataset` lê primeiro os Parquet e, em caso de sucesso, substitui dados,
metadados, IQL e ambiente; limpa snapshots, traces de SoC, referências de run e
experimento e métricas das chaves de análise. Modelos persistidos não são apagados.
Os testes verificam o reset e a preservação do estado se a leitura rejeitar
uma fazenda inexistente. Falhas posteriores à leitura não são transacionais:
não há garantia geral de rollback, nem isolamento concorrente entre clientes.

### R-RUN-002: intercâmbio com o pipeline

O teste `test_qtables_roundtrip_pipeline_mcp` salva pelo motor, carrega via MCP,
reinicia o ambiente no SoC final persistido, salva via MCP e recarrega pelo
motor. Confere tabelas, histórico, configuração e label, sem treinamento.
`save_qtables` sem histórico e sem diretório retorna erro sem criar run.
Runs contêm pickle: carregue somente artefatos confiáveis.

### Passo de ambiente e JSON

`step_environment` rejeita índices inteiros fora dos intervalos antes de
avançar a hora. Um passo válido retorna `reward`, `done`,
`next_state_discrete`, `obs` e `info`. O teste compara a execução com o mesmo
motor e verifica booleanos JSON em tarifas dentro e fora do pico.

O teste revelou um `numpy.bool_` em `info` que impedia a serialização depois
de executar o passo. A fronteira dessa tool agora converte booleanos NumPy
para `bool` nativo. Não mudou a física, as chaves JSON nem o arredondamento.
A correção não certifica serialização de todas as outras tools, tipos de
entrada arbitrários ou comportamento depois do fim do dia.

Os testes de tools exercitam funções diretamente; os testes de transporte
abaixo verificam também serialização e mensagens entre processos. A
[matriz](reorganizacao.md) registra as evidências ligadas à
[visão de domínio](regras-dominio.md).

### R-MCP-004: transporte e cliente

Os testes usam o SDK MCP 1.30.0 para negociar a sessão, listar as 41 tools e
verificar os argumentos obrigatórios de `step_environment`. `initialize` e
`get_state` não aparecem como tools. São exercitados `get_dataset_info`,
`get_observation`, `step_environment`, `reset_environment` e ping.

Um índice fora do intervalo retorna JSON de aplicação com `erro`; tipo de
argumento inválido e tool inexistente retornam `isError` do protocolo. Os
testes verificam que essas rejeições não avançam a hora. Um passo válido
preserva booleanos JSON e seis componentes do estado discreto. Reset volta
à hora zero. O cliente síncrono real do dashboard transforma os dois tipos
de erro em `MCPServerError` e observa a continuidade do estado entre chamadas,
apesar de abrir uma nova sessão MCP para cada chamada.

Cada processo recebe apenas o ambiente-base do SDK e configurações sintéticas,
com `.env` desativado, diretório temporário e loader padrão bloqueado. Não há
treino, leitura de base real ou chamada LLM nesses dois testes. O stdio usa
stdin/stdout reais e o ciclo de encerramento do SDK. O HTTP usa Uvicorn real
em `127.0.0.1`, porta efêmera (`0`), e sinal de prontidão enviado pelo harness
de teste depois do startup. Sem porta fixa, sleeps ou tentativas repetidas.

O harness HTTP observa startup e recebe um comando de parada por stdin;
não substitui as rotas MCP. Em teardown pede encerramento e aguarda o processo,
com término forçado limitado se necessário; o teste normal exige saída zero
e marcador de encerramento. Nenhum endpoint de parada foi adicionado ao produto.

Limites: não testa navegador Streamlit, cliente VS Code/Claude, autenticação,
TLS, proxy remoto, concorrência, carga, todas as tools ou recuperação de queda.
Os subprocessos não são instrumentados pela cobertura configurada no pytest.
O cliente atual usa a API depreciada `streamablehttp_client`; o SDK emitiu
oito avisos de depreciação, mantidos visíveis. Sua migração é tarefa separada.

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
