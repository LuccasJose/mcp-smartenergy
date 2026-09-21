# Graph Report - mcp-smartenergy  (2026-09-21)

## Corpus Check
- 77 files · ~70,944 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1148 nodes · 2125 edges · 73 communities (59 shown, 11 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 141 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0e514028`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- dashboard/state.py
- test_resultados.py
- IQLSystem
- test_bateria_pico_hipoteses.py
- get_state
- smarty_energy/evaluation.py
- tests/conftest.py
- BatteryModel
- test_metrics.py
- dashboard.py
- test_environment.py
- visualization.py
- test_tools.py
- dashboard_web.py
- test_constraints.py
- benchmark.py
- test_env.py
- split_experiments.py
- experiments.py
- MetricsTracker
- judge_core.py
- mcp/server.py
- AgenteQL
- AgentesHeuristicos
- test_experiments.py
- test_tracker.py
- plot_visao_geral_operacional
- verificar_site
- construir_agentes
- PoliticaLLM
- test_baselines.py
- test_transport.py
- test_fisica_unificada.py
- test_data_loader.py
- treinar
- FazendaEnergyEnv
- dashboard/__init__.py
- ajustar_decay
- test_switch_dataset.py
- _carregar_fems
- pages/__init__.py
- RuntimeError
- rodar_rl_mes
- environment.py
- test_fems_dataset_integridade.py
- server.py
- AgenteFinanceiro
- _err
- cobertura_estados
- train_agents
- avaliar_politica
- llm_policy.py
- auditar_base.py
- mcp_server.py
- agents/__init__.py
- .load
- metricas_convergencia
- config.py
- .avaliar
- .get_info
- ServerState
- srv
- resumo_mes
- parametrize
- test_iql_preserva_delegacao_e_selecao_legada
- .agir
- .aprender
- .n_estados
- test_reward_weights_recria_env_global
- test_run_episode_greedy_usa_qtables_para_decisoes_horarias

## God Nodes (most connected - your core abstractions)
1. `FazendaEnergyEnv` - 66 edges
2. `get_state()` - 48 edges
3. `call_tool()` - 37 edges
4. `construir_agentes()` - 32 edges
5. `_err()` - 32 edges
6. `AgenteQL` - 29 edges
7. `BatteryModel` - 27 edges
8. `AgentesHeuristicos` - 26 edges
9. `IQLSystem` - 25 edges
10. `MetricsTracker` - 22 edges

## Surprising Connections (you probably didn't know these)
- `test_agente_ql_greedy_apos_aprendizado()` --calls--> `AgenteQL`  [INFERRED]
  tests/test_environment.py → src/smarty_energy/agents/q_learning.py
- `test_qtables_roundtrip_pipeline_mcp()` --calls--> `construir_agentes()`  [INFERRED]
  tests/mcp/test_tools.py → src/smarty_energy/agents/q_learning.py
- `test_heuristico_decide_acao_para_estado()` --calls--> `AgentesHeuristicos`  [INFERRED]
  tests/mcp/test_baselines.py → src/smarty_energy/agents/rules.py
- `test_semagente_horarios_ingenuos()` --calls--> `SemAgente`  [INFERRED]
  tests/mcp/test_baselines.py → src/smarty_energy/agents/rules.py
- `_rodar_aleatorio()` --uses--> `FazendaEnergyEnv`  [INFERRED]
  tests/test_constraints.py → src/smarty_energy/environment.py

## Import Cycles
- None detected.

## Communities (73 total, 11 thin omitted)

### Community 0 - "dashboard/state.py"
Cohesion: 0.05
Nodes (64): Dashboard Streamlit — SmartEnergy IQL. Rode com: streamlit run…, call_tool(), _call_tool_async(), MCPServerError, ping(), Cliente MCP síncrono usado pelo dashboard Streamlit. O dashboard NÃO importa…, Falha ao chamar uma ferramenta do servidor MCP (conexão ou aplicação)., Chama uma ferramenta MCP e retorna o payload JSON já decodificado. Abre uma… (+56 more)

### Community 1 - "test_resultados.py"
Cohesion: 0.12
Nodes (20): comparar_metrica_pareada(), Compara UMA métrica entre dois braços, pareada por dia (bloco T3). Aplica o…, _max_viol_soc(), _min_economia_pct(), Testes de integração — valida os resultados/números do TCC. Treina os agentes…, Segurança operacional: violações de SoC do RL abaixo do limite tolerado. Sob…, RL deve custar menos do que operar sem gestão., RL deve importar menos energia da rede do que 'sem agente'. (+12 more)

### Community 2 - "IQLSystem"
Cohesion: 0.09
Nodes (13): IQLSystem, Path, Avalia a política greedy dos 3 agentes (ver `avaliar_politica`)., Orquestra os 3 agentes independentes (armazenamento, consumo, gerente). É a API…, Salva as 3 Q-tables em `dir_path/qtable_<nome>.pkl`. Mesmo layout de…, Atualiza hiperparâmetros dos 3 agentes sem destruir as Q-tables., Treina os 3 agentes por `self.n_episodios` e devolve o sumário. Delega a…, SOC final do ep N vira inicial do ep N+1. (+5 more)

### Community 3 - "test_bateria_pico_hipoteses.py"
Cohesion: 0.14
Nodes (25): _cfg_isolado(), _dia(), DataFrame, Testes determinísticos para hipóteses sobre despacho da bateria no pico., Dia controlado cujo primeiro passo basta para testar a bateria., A acao de carga usa apenas excedente; ela nao implementa arbitragem da rede., O IQL distingue fases do pico sem aumentar a tupla de estado., CONFIG com todos os pesos de shaping zerados, exceto os passados. (+17 more)

### Community 4 - "get_state"
Cohesion: 0.07
Nodes (39): configure_reward_weights(), describe_schema(), get_actions(), get_analysis_status(), get_battery_dispatch_stats(), get_current_state(), get_dataset_info(), get_equipment_hourly() (+31 more)

### Community 5 - "smarty_energy/evaluation.py"
Cohesion: 0.16
Nodes (18): classificar_dia(), identificar_cenarios(), DataFrame, ndarray, Funções de avaliação: executa heurístico e RL em dias reais., Executa uma PoliticaLLM em um dia completo (braço 'com MCP'). Clone de…, Identifica os índices dos três cenários de interesse. Returns: dict com chaves…, Categoria de um dia usando quartis da geração e do consumo do mês. Enquanto… (+10 more)

### Community 6 - "tests/conftest.py"
Cohesion: 0.10
Nodes (30): agentes_treinados(), config_teste(), dados_reais(), dia_fake(), dias_reais(), env(), _isola_outputs(), n_ep_teste() (+22 more)

### Community 7 - "BatteryModel"
Cohesion: 0.09
Nodes (23): example, given, settings, BatteryModel, Modelo fisico da bateria do ambiente SmartEnergy., Mantem o estado e aplica as restricoes fisicas da bateria. As entradas de carga…, Armazena energia AC disponivel, respeitando eficiencia e limites., Retira uma fracao do deficit e entrega energia AC a carga. (+15 more)

### Community 8 - "test_metrics.py"
Cohesion: 0.13
Nodes (25): gap_otimalidade(), metricas_dia(), Métricas primárias de desempenho energético (seção 4.1 do Plano de Testes).…, Média diária de cada métrica sobre um mês de simulações. Args: historicos :…, Vetor de uma métrica com um valor por dia — insumo do teste pareado (T3). Ex.:…, Gap de otimalidade (4.1): (custo − ref) ÷ ref. Positivo = pior que a…, Divisão protegida: retorna 0.0 quando o denominador é ~nulo., Calcula as métricas primárias (4.1) e operacionais (4.2) de UM dia. Args:… (+17 more)

### Community 9 - "dashboard.py"
Cohesion: 0.12
Nodes (25): FigureCanvasTkAgg, Frame, Notebook, abrir_dashboard(), _criar_aba_explorar(), _criar_aba_fonte_energia(), _criar_aba_maquina_detalhada(), _criar_aba_visao_geral() (+17 more)

### Community 10 - "test_environment.py"
Cohesion: 0.13
Nodes (10): parametrize, Testes básicos do ambiente, agentes e configuração. Fixtures compartilhadas…, test_agente_ql_greedy_apos_aprendizado(), test_avaliacao_mensal_encadeia_soc_na_ordem(), test_avaliacao_mensal_publica_integra_bateria(), test_avaliacao_mensal_publica_preserva_argumentos(), test_env_carga_rede_limiar_tarifario(), test_env_carga_rede_prioriza_excedente() (+2 more)

### Community 11 - "visualization.py"
Cohesion: 0.14
Nodes (25): _media_movel(), plot_cenarios(), plot_comparacao_dia(), plot_comparativo_3vias(), plot_curvas_aprendizado(), plot_explorar_dia(), plot_maquina_detalhada(), plot_tradeoff_mcp() (+17 more)

### Community 13 - "dashboard_web.py"
Cohesion: 0.13
Nodes (19): Dash, abrir_dashboard_web(), _content_runs(), criar_app(), _fig_explorar_dia(), _fig_maquina_detalhada(), _fig_visao_geral(), _labels_dias() (+11 more)

### Community 14 - "test_constraints.py"
Cohesion: 0.08
Nodes (10): execucoes(), fixture, Validação das restrições rígidas (HARD) do ambiente. Estas restrições devem…, R-BALANCO (T1.1): a identidade energética horária fecha em TODOS os termos.…, R-SOC dinâmica (T1.2): SoC evolui exatamente pelo fluxo líquido da bateria.…, (politica, indice_dia, dia_df, historico) para todos os dias × políticas., _rodar_aleatorio(), _rodar_manter() (+2 more)

### Community 15 - "benchmark.py"
Cohesion: 0.13
Nodes (21): custo_api_brl(), custos_por_dia(), imprimir_relatorio(), _media_op(), _media_resumos(), _phi(), PrecoModelo, Benchmark: política de controle RL puro × LLM-via-MCP (análise de trade-offs).… (+13 more)

### Community 16 - "test_env.py"
Cohesion: 0.09
Nodes (13): Invariantes fisicos e comportamentais do FazendaEnergyEnv., Sede real fica em [0.8, 1.2] * sede_ideal., Mesmo o agente tentando cortar (a_cons=4), o rescue tardio deve fazer o secador…, Sanity: com todos os pesos 0 e sem violacao, o reward vira so o offset. Com…, SOC=100 deve cair no ultimo bucket (9), nao em 10., Bomba liga exatamente nas horas em BOMBA_HORAS_ON, independente da acao., Pivo so pode ser ativado uma vez por dia, e fica ON por 8h consecutivas., test_bomba_schedule_fixo() (+5 more)

### Community 17 - "split_experiments.py"
Cohesion: 0.07
Nodes (40): construir_divisoes(), datas_dos_dias(), descrever_divisao(), Divisao, inicios_de_blocos(), Particoes por dias completos, sem executar ou modificar o motor de RL., Exige dias completos, unicos e ordenados, de uma unica base/fazenda., Constroi somente os metodos explicitamente selecionados. Sazonal estratifica… (+32 more)

### Community 18 - "experiments.py"
Cohesion: 0.17
Nodes (20): avisos_fisica(), caminho(), carregar(), _escrever_meta(), _ler_meta(), listar(), mais_recente(), _meta_path() (+12 more)

### Community 19 - "MetricsTracker"
Cohesion: 0.06
Nodes (23): MetricsTracker, Rastreia todas as métricas de passos e episódios para cada agente. Métricas por…, Resume carga, descarga e bloqueios da bateria por período tarifário., Agrega violações por hora-do-dia para diagnóstico do LLM-juiz. Retorna, para…, Uso médio por hora-do-dia de cada equipamento (kW), agregando dias. Inclui…, KPIs por equipamento (lógica de BI): energia, horas ligada, pico, custo.…, Retorna as 24 entradas de info do último episódio registrado., cfg() (+15 more)

### Community 20 - "judge_core.py"
Cohesion: 0.17
Nodes (14): main(), _on_event(), LLM-as-a-judge local usando Qwen3 (via Ollama, em GPU) sobre o servidor MCP.…, _extract_text(), _mcp_tools_to_openai(), ollama_disponivel(), Loop do LLM-as-a-judge, reutilizável pelo CLI (`judge.py`) e pelo dashboard. O…, Wrapper síncrono de `run_judge` (uso no Streamlit e em scripts simples). (+6 more)

### Community 21 - "mcp/server.py"
Cohesion: 0.12
Nodes (14): Camada MCP do SmartEnergy. `server.py` expõe o sistema multi-agente como ~25…, configure_agents(), evaluate_split_test(), export_all_data(), get_equipment_stats(), get_qtables_info(), MCP Server — SmartEnergy IQL (3 agentes Q-Learning cooperativos). Expõe…, Avança 1 hora no env atual com as 3 ações fornecidas. a_arm: 0=solar, 1=manter,… (+6 more)

### Community 22 - "AgenteQL"
Cohesion: 0.11
Nodes (19): AgenteQL, Agente de Q-Learning com política epsilon-greedy. Todos os agentes recebem o…, Reduz epsilon multiplicativamente (decaimento exponencial)., AgenteQL (hysteretic) e IQLSystem., TD>0 → atualizacao com taxa alpha (otimista)., TD<0 → atualizacao com taxa beta (pessimista, beta << alpha)., Janela rolante de td_errors limita o tamanho., test_agir_devolve_acao_valida() (+11 more)

### Community 23 - "AgentesHeuristicos"
Cohesion: 0.19
Nodes (8): AgentesHeuristicos, Baseline com regras fixas para comparação com o RL. Implementa o índice de…, Índice de estresse financeiro (0–100)., Regra: carrega com sol, descarrega no pico tarifário., Regra: corta cargas pelo nível de estresse financeiro. Mapeamento 0-7: bit 0:…, Regra: define teto de consumo pelo nível de estresse., As três ações da hora, a partir do estresse financeiro do estado., test_heuristica_retorna_acoes_validas()

### Community 24 - "test_experiments.py"
Cohesion: 0.20
Nodes (11): _popular_politica(), fixture, Experimentos — modelos salvos (par RL padrão + RL + LLM MCP). Round-trip…, Servidor com dataset fake e experimentos gravados em tmp_path., Simula um treino: povoa as Q-tables e o hist sem rodar episódios., srv(), test_encoding_incompativel_recusa_load(), test_label_default_usa_n_episodios() (+3 more)

### Community 25 - "test_tracker.py"
Cohesion: 0.24
Nodes (10): _info_passo(), test_battery_dispatch_stats_separa_origem_e_custo_da_carga(), test_battery_dispatch_stats_separa_pico_e_motivos_de_bloqueio(), test_equipment_hourly_agrega_medias(), test_equipment_stats_kpis(), test_get_eval_metrics_calcula_media(), test_hourly_violations_agrega_por_hora(), test_limpar_por_chave() (+2 more)

### Community 26 - "plot_visao_geral_operacional"
Cohesion: 0.24
Nodes (11): _tabela_kpis(), _custo_por_maquina(), _custo_real_por_maquina(), _custos_estrategia(), _kpis_maquinas(), plot_visao_geral_operacional(), Calcula KPIs operacionais por máquina ao longo de todos os dias., Custo teórico (R$) por máquina = Σ kWh × tarifa(hora). Não desconta… (+3 more)

### Community 27 - "verificar_site"
Cohesion: 0.20
Nodes (11): HTMLParser, main(), PaginaHTML, Path, Verifica links locais no HTML gerado, sem acessar rede ou importar o motor., verificar_site(), parametrize, Verificacoes do validador documental com HTML sintetico, sem Retype ou rede. (+3 more)

### Community 28 - "construir_agentes"
Cohesion: 0.07
Nodes (57): construir_agentes(), Instancia os três agentes Q-Learning com os tamanhos de ação padrão. Fonte…, _card_meta(), carregar_rl_padrao(), Salva as 3 Q-tables do treino atual. Sem `dir_path`, grava um run versionado em…, Define o braço 'RL padrão' a partir de um run treinado (ex.: Smart_Energy).…, save_qtables(), alternar_favorito() (+49 more)

### Community 29 - "PoliticaLLM"
Cohesion: 0.17
Nodes (8): EventoDecisao, PoliticaLLM, Decide as 3 ações para o estado atual, registrando métricas. Nunca levanta…, Agrega os EventoDecisao em métricas do Eixo 2., Resultado bruto de um decisor para uma única decisão. ``acoes`` é None quando o…, Métrica operacional de uma decisão (Eixo 2 do benchmark)., Política de controle por LLM, plugável no harness de avaliação. Args: decisor :…, RespostaDecisor

### Community 30 - "test_baselines.py"
Cohesion: 0.15
Nodes (12): AgentesHeuristicos e SemAgente., Sol alto + SOC < 80 deve disparar a_arm=0 (carregar)., Tarifa > 0.9 + SOC saudavel deve disparar descarga integral., Stress crescente → mais cargas cortadas (bitmask cresce)., Stress alto → teto conservador., test_heuristico_carrega_com_sol_alto_e_soc_baixo(), test_heuristico_consumo_corta_proporcional_ao_stress(), test_heuristico_decide_acao_para_estado() (+4 more)

### Community 31 - "test_transport.py"
Cohesion: 0.21
Nodes (10): _ambiente_isolado(), _chamar_json(), dados_transporte(), fixture, parametrize, Contratos MCP pelo transporte real, com dados e processos isolados., servidor_http(), test_dependencias_dev_exigem_api_mcp_utilizada() (+2 more)

### Community 32 - "test_fisica_unificada.py"
Cohesion: 0.14
Nodes (13): arquitetura_isolada(), fixture, parametrize, Item 2 — trava a igualdade de física entre o pipeline e a camada MCP. Depois da…, Servidor MCP inicializado explicitamente com fixtures sinteticas., Não deve existir smarty_energy.mcp.{config,environment,energy_env,agents}., Preenche as Q-tables com valores determinísticos para todo o espaço. Um agente…, _semear_qtables() (+5 more)

### Community 33 - "test_data_loader.py"
Cohesion: 0.17
Nodes (5): Testes do carregamento de dados (data_loader) sobre a base real local. Todos os…, A tarifa no pico (18h–21h) deve ser maior que a média fora do pico., Não deve haver geração solar entre 0h e 4h., test_geracao_solar_zero_de_madrugada(), test_tarifa_pico_maior_que_fora_pico()

### Community 34 - "treinar"
Cohesion: 0.13
Nodes (19): DataFrame, ndarray, Treina os três agentes por `cfg['n_episodios']` episódios. Cada episódio simula…, treinar(), historico_treino(), fixture, parametrize, Bloco T2 — verificação do treinamento Q-learning (sem itens de seed). Cobre:… (+11 more)

### Community 35 - "FazendaEnergyEnv"
Cohesion: 0.20
Nodes (8): BatteryFlow, Resultado de uma operacao de carga ou descarga., FazendaEnergyEnv, DataFrame, ndarray, Executa um timestep (1 hora). Args: a_arm : bateria (0=solar, 1=manter,…, Reinicia o ambiente para um novo dia., Estado descritivo para inspeção externa (tools MCP get_current_state).

### Community 37 - "ajustar_decay"
Cohesion: 0.20
Nodes (12): ajustar_decay(), Copia `cfg` para um treino de `n_episodios`, reescalando o decaimento de ε. O…, initialize(), _log(), main(), Sobe o servidor MCP (chamado pelo `server.py` da raiz do projeto)., Treina e valida uma divisao escolhida; nao abre o teste final. Repetir a mesma…, Log do servidor — sempre em stderr, para não poluir o canal do protocolo. (+4 more)

### Community 38 - "test_switch_dataset.py"
Cohesion: 0.22
Nodes (5): dataset_fems(), fixture, switch_dataset — troca da fazenda ativa no servidor (reset completo). Usa…, 2 dias de fevereiro/2025 da fazenda FAZ-X (formato FEMS)., srv()

### Community 39 - "_carregar_fems"
Cohesion: 0.12
Nodes (26): _baixar_excel_drive(), carregar_dados(), _carregar_fems(), descrever_base(), DataFrame, ndarray, Carrega dados de geração, consumo e tarifa da base nova. Prioridade da fonte:…, Metadados descritivos da base carregada (tool MCP `get_dataset_info`). Separado… (+18 more)

### Community 41 - "RuntimeError"
Cohesion: 0.39
Nodes (7): RuntimeError, check_call(), check_context7(), load_servers(), main(), Verifica os MCPs auxiliares sem importar o motor ou ler dados privados., test_initialize_falha_permite_nova_tentativa()

### Community 42 - "rodar_rl_mes"
Cohesion: 0.27
Nodes (12): Roda `rodar_dia(dia, soc_inicial)` em todos os dias, na ordem. Com…, rodar_heuristico_mes(), _rodar_mes(), rodar_rl_mes(), rodar_sem_agente_mes(), As 3 estratégias custam o mesmo pelo MCP e pelo pipeline. O teste acima trava a…, test_compare_strategies_bate_com_o_pipeline(), avaliacao() (+4 more)

### Community 43 - "environment.py"
Cohesion: 0.23
Nodes (7): executar_seed(), main(), Avalia a estabilidade do despacho da bateria em múltiplas seeds. Uso:…, _resumo(), FazendaEnergyEnv — Ambiente de simulação energética da fazenda. Estado discreto…, Estado operacional do MCP; reutiliza os componentes do motor., Loop de treinamento IQL (Independent Q-Learning) cooperativo.

### Community 44 - "test_fems_dataset_integridade.py"
Cohesion: 0.13
Nodes (8): fems(), fixture, Integridade do dataset FEMS versionado em dados/fems_faz_002 (fonte padrão).…, O padrão do projeto agora é a cópia versionada (offline)., Σ(cargas) e Σ(geração) do loader devem bater com consumo_fatura., test_ambiente_roda_um_dia_sem_violacoes_estruturais(), test_balanco_energetico_bate_com_fatura(), test_config_aponta_para_dataset_versionado()

### Community 49 - "AgenteFinanceiro"
Cohesion: 0.29
Nodes (4): AgenteFinanceiro, Calcula o estresse financeiro baseado na tarifa e saldo de créditos., Atualiza o saldo de créditos (simplificado: 1 para 1)., Implementa a lógica de monitoramento de custos e créditos solares. Traduz o…

### Community 50 - "_err"
Cohesion: 0.09
Nodes (22): Exception, _err(), evaluate_agents(), get_financeiro_state(), get_split_experiment(), health_report(), list_experiments(), load_experiment() (+14 more)

### Community 51 - "cobertura_estados"
Cohesion: 0.50
Nodes (4): cobertura_estados(), Fração do espaço de estados discretos visitada no treino (bloco T2). Estados…, A cobertura deve ser reportável e estar em (0, 1]. O valor em si é o dado que…, test_cobertura_estados_reportada()

### Community 52 - "train_agents"
Cohesion: 0.20
Nodes (10): compare_strategies(), _congelar_politica(), _pesos_sao_default(), Congela a política IQL atual (cópia das Q-tables) sob um nome. O braço 'RL…, Copia as Q-tables atuais do IQL sob `nome` em state.snapshots., True se nenhum peso do reward foi alterado (o LLM-juiz ainda não agiu)., Treina os 3 agentes IQL com reward cooperativo. Dias percorridos…, Compara as 4 estratégias do projeto nos mesmos n_dias do dataset. Braços… (+2 more)

### Community 53 - "avaliar_politica"
Cohesion: 0.33
Nodes (5): avaliar_politica(), Laco de avaliacao compartilhado pelas politicas, sem atualizar Q-tables., Roda uma política por `n_dias` e devolve as métricas médias diárias. Fonte…, A avaliação encadeia o SoC final de um dia no reset do dia seguinte., test_avaliacao_com_propagacao_inicia_dia_seguinte_no_soc_anterior()

### Community 54 - "llm_policy.py"
Cohesion: 0.17
Nodes (11): acoes_validas(), criar_decisor_anthropic(), decisor_heuristico_simulado(), decisor_stub(), _estado_para_texto(), Política de controle baseada em LLM (braço "com MCP" do benchmark). Substitui…, Decisor offline determinístico (testes/validação sem custo de API). Por padrão…, Decisor que imita o heurístico — útil para checar o caminho 'válido' da… (+3 more)

### Community 55 - "auditar_base.py"
Cohesion: 0.47
Nodes (5): _abas(), _fmt(), main(), Auditoria de fidelidade à base v8 (itens 1 e 4 do plano de verificações). Fonte…, OK se |atual-base|/base <= tol; senão marca a divergência.

### Community 56 - "mcp_server.py"
Cohesion: 0.20
Nodes (9): construir_servidor(), definir_estado(), Servidor MCP que expõe o ambiente de energia como ferramentas (braço "LLM-via-…, Publica o estado da hora corrente para a tool ``estado_atual``., Devolve a última decisão registrada pelo LLM via ``decidir_controle``., Valida e registra uma decisão (compartilhado pela tool MCP)., Constrói o servidor FastMCP com as duas tools (import tardio do SDK)., _registrar_decisao() (+1 more)

### Community 57 - "agents/__init__.py"
Cohesion: 0.40
Nodes (3): API publica dos agentes, preservada apos a separacao por responsabilidade. Os…, Q-learning histeretico e construcao da topologia cooperativa., Orquestracao dos agentes IQL; delega treinamento ao motor compartilhado.

### Community 58 - ".load"
Cohesion: 0.40
Nodes (3): Path, Carrega uma Q-table salva anteriormente., Persiste a Q-table em disco via pickle.

### Community 59 - "metricas_convergencia"
Cohesion: 0.33
Nodes (6): metricas_convergencia(), Mede a estabilização de uma série de treino (bloco T2 — convergência). Compara…, A função de convergência distingue série estável de série ainda em queda., T2.3: a curva de custo por episódio estabiliza ao fim do treino., test_metricas_convergencia_serie_curta_e_sintetica(), test_treino_converge()

### Community 60 - "config.py"
Cohesion: 0.18
Nodes (9): construir_artefatos(), main(), SmartEnergy MAS — Pipeline principal. Execução completa: 1. Carrega dados do…, Recarrega um run e monta RES_R + todas as figuras/dados do dashboard. Tudo que…, Regras deterministicas de estresse financeiro e politicas de referencia., Cenário sem gestão nenhuma — a fazenda 'como está hoje'. Sem otimização: a…, SemAgente, delta_pct() (+1 more)

### Community 63 - "ServerState"
Cohesion: 0.50
Nodes (4): Uma analise ativa no processo, sem isolamento concorrente por cliente., ServerState, test_estado_unico_concentra_objetos(), test_estados_nao_compartilham_snapshots_por_padrao()

### Community 64 - "srv"
Cohesion: 0.50
Nodes (4): fixture, Inicializa o servidor com fixtures sinteticas, sem fontes externas., srv(), srv_sem_dados()

### Community 65 - "resumo_mes"
Cohesion: 0.40
Nodes (5): slow, Calcula métricas médias diárias para um mês de simulações. Args: historicos :…, resumo_mes(), Mesma semente → mesmo resultado de avaliação (determinismo)., test_reprodutibilidade_mesma_semente()

### Community 66 - "parametrize"
Cohesion: 0.50
Nodes (4): parametrize, test_main_inicializa_antes_do_transporte(), test_step_environment_preserva_contrato_do_motor(), test_step_environment_rejeita_indices_sem_avancar()

### Community 67 - "test_iql_preserva_delegacao_e_selecao_legada"
Cohesion: 0.67
Nodes (3): parametrize, test_importacao_em_processo_novo_sem_ciclo(), test_iql_preserva_delegacao_e_selecao_legada()

## Knowledge Gaps
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_state()` connect `get_state` to `smarty_energy/evaluation.py`, `ajustar_decay`, `_carregar_fems`, `RuntimeError`, `_err`, `experiments.py`, `train_agents`, `mcp/server.py`, `construir_agentes`, `ServerState`?**
  _High betweenness centrality (0.137) - this node is a cross-community bridge._
- **Why does `MCPServerError` connect `dashboard/state.py` to `RuntimeError`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Why does `FazendaEnergyEnv` connect `FazendaEnergyEnv` to `IQLSystem`, `test_bateria_pico_hipoteses.py`, `get_state`, `smarty_energy/evaluation.py`, `tests/conftest.py`, `BatteryModel`, `test_metrics.py`, `test_environment.py`, `test_constraints.py`, `test_env.py`, `MetricsTracker`, `mcp/server.py`, `test_baselines.py`, `treinar`, `ajustar_decay`, `_carregar_fems`, `environment.py`, `test_fems_dataset_integridade.py`, `_err`, `train_agents`, `avaliar_politica`, `config.py`, `ServerState`, `parametrize`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Are the 46 inferred relationships involving `FazendaEnergyEnv` (e.g. with `executar_seed()` and `avaliar_politica()`) actually correct?**
  _`FazendaEnergyEnv` has 46 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `get_state()` (e.g. with `RuntimeError` and `ServerState`) actually correct?**
  _`get_state()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `construir_agentes()` (e.g. with `main()` and `executar_seed()`) actually correct?**
  _`construir_agentes()` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Should `dashboard/state.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05128205128205128 - nodes in this community are weakly interconnected._