# Graph Report - mcp-smartenergy  (2026-09-20)

## Corpus Check
- 73 files · ~70,335 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1131 nodes · 2092 edges · 65 communities (55 shown, 7 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 123 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `1a74539d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- dashboard/state.py
- test_resultados.py
- test_runs.py
- FazendaEnergyEnv
- get_state
- evaluation.py
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
- PlanoDivisoes
- experiments.py
- MetricsTracker
- judge_core.py
- IQLSystem
- test_agent.py
- Path
- test_experiments.py
- test_tracker.py
- plot_visao_geral_operacional
- verificar_site
- runs.py
- PoliticaLLM
- AgentesHeuristicos
- test_transport.py
- test_fisica_unificada.py
- test_data_loader.py
- construir_agentes
- AgenteQL
- dashboard/__init__.py
- ServerState
- test_switch_dataset.py
- _carregar_fems
- pages/__init__.py
- carregar_run
- rodar_rl_mes
- mcp/server.py
- test_fems_dataset_integridade.py
- server.py
- salvar_run
- _err
- cobertura_estados
- train_agents
- run_episode
- llm_policy.py
- auditar_base.py
- mcp_server.py
- SemAgente
- ler_meta
- metricas_convergencia
- main
- get_analysis_status
- health_report
- rename_experiment
- resumo_mes

## God Nodes (most connected - your core abstractions)
1. `FazendaEnergyEnv` - 67 edges
2. `get_state()` - 48 edges
3. `call_tool()` - 37 edges
4. `_err()` - 32 edges
5. `construir_agentes()` - 29 edges
6. `AgentesHeuristicos` - 28 edges
7. `BatteryModel` - 27 edges
8. `AgenteQL` - 26 edges
9. `IQLSystem` - 22 edges
10. `MetricsTracker` - 22 edges

## Surprising Connections (you probably didn't know these)
- `test_agir_devolve_acao_valida()` --uses--> `AgenteQL`  [INFERRED]
  tests/mcp/test_agent.py → src/smarty_energy/agents.py
- `test_aprender_incrementa_n_updates()` --uses--> `AgenteQL`  [INFERRED]
  tests/mcp/test_agent.py → src/smarty_energy/agents.py
- `test_epsilon_decay()` --uses--> `AgenteQL`  [INFERRED]
  tests/mcp/test_agent.py → src/smarty_energy/agents.py
- `test_save_load_preserva_qtable()` --uses--> `AgenteQL`  [INFERRED]
  tests/mcp/test_agent.py → src/smarty_energy/agents.py
- `test_agente_ql_acao_valida()` --uses--> `AgenteQL`  [INFERRED]
  tests/test_environment.py → src/smarty_energy/agents.py

## Import Cycles
- None detected.

## Communities (65 total, 7 thin omitted)

### Community 0 - "dashboard/state.py"
Cohesion: 0.05
Nodes (64): Dashboard Streamlit — SmartEnergy IQL. Rode com: streamlit run…, call_tool(), _call_tool_async(), MCPServerError, ping(), Cliente MCP síncrono usado pelo dashboard Streamlit. O dashboard NÃO importa…, Falha ao chamar uma ferramenta do servidor MCP (conexão ou aplicação)., Chama uma ferramenta MCP e retorna o payload JSON já decodificado. Abre uma… (+56 more)

### Community 1 - "test_resultados.py"
Cohesion: 0.12
Nodes (20): comparar_metrica_pareada(), Compara UMA métrica entre dois braços, pareada por dia (bloco T3). Aplica o…, _max_viol_soc(), _min_economia_pct(), Testes de integração — valida os resultados/números do TCC. Treina os agentes…, Segurança operacional: violações de SoC do RL abaixo do limite tolerado. Sob…, RL deve custar menos do que operar sem gestão., RL deve importar menos energia da rede do que 'sem agente'. (+12 more)

### Community 2 - "test_runs.py"
Cohesion: 0.22
Nodes (12): Valida um run recarregado contra a discretização e a física atuais. Levanta…, verificar_compatibilidade(), fixture, parametrize, Compatibilidade de runs persistidos com a codificação atual de estados., runs_isolados(), test_carregar_run_rejeita_numero_de_acoes(), test_run_com_chave_invalida_e_rejeitado() (+4 more)

### Community 3 - "FazendaEnergyEnv"
Cohesion: 0.07
Nodes (43): AgenteFinanceiro, Implementa a lógica de monitoramento de custos e créditos solares. Traduz o…, Calcula o estresse financeiro baseado na tarifa e saldo de créditos., Atualiza o saldo de créditos (simplificado: 1 para 1)., FazendaEnergyEnv, DataFrame, ndarray, Executa um timestep (1 hora). Args: a_arm : bateria (0=solar, 1=manter,… (+35 more)

### Community 4 - "get_state"
Cohesion: 0.07
Nodes (41): configure_agents(), describe_schema(), get_battery_dispatch_stats(), get_current_state(), get_dataset_info(), get_equipment_hourly(), get_equipment_stats(), get_eval_metrics() (+33 more)

### Community 5 - "evaluation.py"
Cohesion: 0.15
Nodes (18): classificar_dia(), delta_pct(), identificar_cenarios(), DataFrame, ndarray, Funções de avaliação: executa heurístico e RL em dias reais., Executa uma PoliticaLLM em um dia completo (braço 'com MCP'). Clone de…, Retorna variação percentual formatada de a para b. (+10 more)

### Community 6 - "tests/conftest.py"
Cohesion: 0.10
Nodes (30): agentes_treinados(), config_teste(), dados_reais(), dia_fake(), dias_reais(), env(), _isola_outputs(), n_ep_teste() (+22 more)

### Community 7 - "BatteryModel"
Cohesion: 0.08
Nodes (25): example, given, settings, BatteryFlow, BatteryModel, Modelo fisico da bateria do ambiente SmartEnergy., Resultado de uma operacao de carga ou descarga., Mantem o estado e aplica as restricoes fisicas da bateria. As entradas de carga… (+17 more)

### Community 8 - "test_metrics.py"
Cohesion: 0.13
Nodes (25): gap_otimalidade(), metricas_dia(), Métricas primárias de desempenho energético (seção 4.1 do Plano de Testes).…, Média diária de cada métrica sobre um mês de simulações. Args: historicos :…, Vetor de uma métrica com um valor por dia — insumo do teste pareado (T3). Ex.:…, Gap de otimalidade (4.1): (custo − ref) ÷ ref. Positivo = pior que a…, Divisão protegida: retorna 0.0 quando o denominador é ~nulo., Calcula as métricas primárias (4.1) e operacionais (4.2) de UM dia. Args:… (+17 more)

### Community 9 - "dashboard.py"
Cohesion: 0.12
Nodes (25): FigureCanvasTkAgg, Frame, Notebook, abrir_dashboard(), _criar_aba_explorar(), _criar_aba_fonte_energia(), _criar_aba_maquina_detalhada(), _criar_aba_visao_geral() (+17 more)

### Community 10 - "test_environment.py"
Cohesion: 0.11
Nodes (13): parametrize, Testes básicos do ambiente, agentes e configuração. Fixtures compartilhadas…, test_agente_ql_acao_valida(), test_agente_ql_greedy_apos_aprendizado(), test_agente_ql_save_load(), test_avaliacao_mensal_encadeia_soc_na_ordem(), test_avaliacao_mensal_publica_integra_bateria(), test_avaliacao_mensal_publica_preserva_argumentos() (+5 more)

### Community 11 - "visualization.py"
Cohesion: 0.14
Nodes (25): _media_movel(), plot_cenarios(), plot_comparacao_dia(), plot_comparativo_3vias(), plot_curvas_aprendizado(), plot_explorar_dia(), plot_maquina_detalhada(), plot_tradeoff_mcp() (+17 more)

### Community 12 - "test_tools.py"
Cohesion: 0.05
Nodes (23): RuntimeError, check_call(), check_context7(), load_servers(), main(), Verifica os MCPs auxiliares sem importar o motor ou ler dados privados., fixture, parametrize (+15 more)

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

### Community 17 - "PlanoDivisoes"
Cohesion: 0.07
Nodes (38): construir_divisoes(), datas_dos_dias(), descrever_divisao(), Divisao, inicios_de_blocos(), Particoes por dias completos, sem executar ou modificar o motor de RL., Exige dias completos, unicos e ordenados, de uma unica base/fazenda., Constroi somente os metodos explicitamente selecionados. Sazonal estratifica… (+30 more)

### Community 18 - "experiments.py"
Cohesion: 0.14
Nodes (23): avisos_fisica(), caminho(), carregar(), _escrever_meta(), _ler_meta(), listar(), mais_recente(), _meta_path() (+15 more)

### Community 19 - "MetricsTracker"
Cohesion: 0.06
Nodes (23): MetricsTracker, Rastreia todas as métricas de passos e episódios para cada agente. Métricas por…, Resume carga, descarga e bloqueios da bateria por período tarifário., Agrega violações por hora-do-dia para diagnóstico do LLM-juiz. Retorna, para…, Uso médio por hora-do-dia de cada equipamento (kW), agregando dias. Inclui…, KPIs por equipamento (lógica de BI): energia, horas ligada, pico, custo.…, Retorna as 24 entradas de info do último episódio registrado., cfg() (+15 more)

### Community 20 - "judge_core.py"
Cohesion: 0.17
Nodes (14): main(), _on_event(), LLM-as-a-judge local usando Qwen3 (via Ollama, em GPU) sobre o servidor MCP.…, _extract_text(), _mcp_tools_to_openai(), ollama_disponivel(), Loop do LLM-as-a-judge, reutilizável pelo CLI (`judge.py`) e pelo dashboard. O…, Wrapper síncrono de `run_judge` (uso no Streamlit e em scripts simples). (+6 more)

### Community 21 - "IQLSystem"
Cohesion: 0.15
Nodes (5): IQLSystem, Orquestra os 3 agentes independentes (armazenamento, consumo, gerente). É a API…, Atualiza hiperparâmetros dos 3 agentes sem destruir as Q-tables., Treina os 3 agentes por `self.n_episodios` e devolve o sumário. Delega a…, Avalia a política greedy dos 3 agentes (ver `avaliar_politica`).

### Community 22 - "test_agent.py"
Cohesion: 0.13
Nodes (13): AgenteQL (hysteretic) e IQLSystem., TD>0 → atualizacao com taxa alpha (otimista)., TD<0 → atualizacao com taxa beta (pessimista, beta << alpha)., Janela rolante de td_errors limita o tamanho., SOC final do ep N vira inicial do ep N+1., test_agir_devolve_acao_valida(), test_aprender_incrementa_n_updates(), test_epsilon_decay() (+5 more)

### Community 23 - "Path"
Cohesion: 0.25
Nodes (4): Path, Persiste a Q-table em disco via pickle., Carrega uma Q-table salva anteriormente., Salva as 3 Q-tables em `dir_path/qtable_<nome>.pkl`. Mesmo layout de…

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

### Community 28 - "runs.py"
Cohesion: 0.18
Nodes (18): caminho_run(), definir_latest(), deletar_run(), _escrever_meta(), ler_historico(), listar_run_ids(), listar_runs(), migrar_legado() (+10 more)

### Community 29 - "PoliticaLLM"
Cohesion: 0.14
Nodes (10): acoes_validas(), EventoDecisao, PoliticaLLM, Decide as 3 ações para o estado atual, registrando métricas. Nunca levanta…, Agrega os EventoDecisao em métricas do Eixo 2., Resultado bruto de um decisor para uma única decisão. ``acoes`` é None quando o…, Métrica operacional de uma decisão (Eixo 2 do benchmark)., Valida que a tripla está dentro do espaço de ações do ambiente. (+2 more)

### Community 30 - "AgentesHeuristicos"
Cohesion: 0.10
Nodes (19): AgentesHeuristicos, Baseline com regras fixas para comparação com o RL. Implementa o índice de…, Índice de estresse financeiro (0–100)., Regra: carrega com sol, descarrega no pico tarifário., Regra: corta cargas pelo nível de estresse financeiro. Mapeamento 0-7: bit 0:…, Regra: define teto de consumo pelo nível de estresse., As três ações da hora, a partir do estresse financeiro do estado., AgentesHeuristicos e SemAgente. (+11 more)

### Community 31 - "test_transport.py"
Cohesion: 0.21
Nodes (10): _ambiente_isolado(), _chamar_json(), dados_transporte(), fixture, parametrize, Contratos MCP pelo transporte real, com dados e processos isolados., servidor_http(), test_dependencias_dev_exigem_api_mcp_utilizada() (+2 more)

### Community 32 - "test_fisica_unificada.py"
Cohesion: 0.14
Nodes (13): arquitetura_isolada(), fixture, parametrize, Item 2 — trava a igualdade de física entre o pipeline e a camada MCP. Depois da…, Não deve existir smarty_energy.mcp.{config,environment,energy_env,agents}., Preenche as Q-tables com valores determinísticos para todo o espaço. Um agente…, Servidor MCP inicializado explicitamente com fixtures sinteticas., _semear_qtables() (+5 more)

### Community 33 - "test_data_loader.py"
Cohesion: 0.17
Nodes (5): Testes do carregamento de dados (data_loader) sobre a base real local. Todos os…, A tarifa no pico (18h–21h) deve ser maior que a média fora do pico., Não deve haver geração solar entre 0h e 4h., test_geracao_solar_zero_de_madrugada(), test_tarifa_pico_maior_que_fora_pico()

### Community 34 - "construir_agentes"
Cohesion: 0.18
Nodes (13): construir_agentes(), Instancia os três agentes Q-Learning com os tamanhos de ação padrão. Fonte…, historico_treino(), fixture, Bloco T2 — verificação do treinamento Q-learning (sem itens de seed). Cobre:…, Roda uma política totalmente aleatória em todos os dias (determinística)., Treina um run de 3000 ep e devolve o histórico (rewards/custos por ep). 2000 ep…, O total combinatório deve ser 7·10·3·3·2·3 = 3780 (fonte única). (+5 more)

### Community 35 - "AgenteQL"
Cohesion: 0.13
Nodes (9): AgenteQL, Agente de Q-Learning com política epsilon-greedy. Todos os agentes recebem o…, Seleciona uma ação via política epsilon-greedy. Usa o RNG global do NumPy de…, Atualização Q-Learning: Q[s][a] += α(r + γ·max(Q[s']) - Q[s][a])., Reduz epsilon multiplicativamente (decaimento exponencial)., Número de estados distintos visitados., Média e desvio do |TD-error| na janela final — proxy de convergência., Resumo do agente para diagnóstico (tools MCP e health_report). (+1 more)

### Community 37 - "ServerState"
Cohesion: 0.18
Nodes (12): initialize(), _log(), main(), Sobe o servidor MCP (chamado pelo `server.py` da raiz do projeto)., Treina e valida uma divisao escolhida; nao abre o teste final. Repetir a mesma…, Log do servidor — sempre em stderr, para não poluir o canal do protocolo., Treina, num só passo, DUAS políticas independentes com o mesmo nº de episódios:…, Prepara o estado uma vez; chamadas Python diretas devem inicializar antes. O… (+4 more)

### Community 38 - "test_switch_dataset.py"
Cohesion: 0.22
Nodes (5): dataset_fems(), fixture, switch_dataset — troca da fazenda ativa no servidor (reset completo). Usa…, 2 dias de fevereiro/2025 da fazenda FAZ-X (formato FEMS)., srv()

### Community 39 - "_carregar_fems"
Cohesion: 0.12
Nodes (26): _baixar_excel_drive(), carregar_dados(), _carregar_fems(), descrever_base(), DataFrame, ndarray, Carrega dados de geração, consumo e tarifa da base nova. Prioridade da fonte:…, Metadados descritivos da base carregada (tool MCP `get_dataset_info`). Separado… (+18 more)

### Community 41 - "carregar_run"
Cohesion: 0.25
Nodes (8): carregar_rl_padrao(), Define o braço 'RL padrão' a partir de um run treinado (ex.: Smart_Energy).…, carregar_run(), Carrega as Q-tables do run em ``agentes`` e devolve o histórico. Os agentes…, Carrega um run e roda o RL em todos os dias. Retorna ``(res_r, hist)`` onde…, resultados_rl(), test_carregar_run_ausente_falha(), test_run_roundtrip_preserva_politica_historico_e_config()

### Community 42 - "rodar_rl_mes"
Cohesion: 0.22
Nodes (14): Roda `rodar_dia(dia, soc_inicial)` em todos os dias, na ordem. Com…, Executa os agentes RL treinados em modo greedy (sem exploração). Returns:…, rodar_heuristico_mes(), _rodar_mes(), rodar_rl(), rodar_rl_mes(), rodar_sem_agente_mes(), As 3 estratégias custam o mesmo pelo MCP e pelo pipeline. O teste acima trava a… (+6 more)

### Community 43 - "mcp/server.py"
Cohesion: 0.15
Nodes (19): executar_seed(), main(), Avalia a estabilidade do despacho da bateria em múltiplas seeds. Uso:…, _resumo(), avaliar_politica(), Agentes do sistema SmartEnergy MAS. AgenteQL — Q-Learning independente (IQL)…, Roda uma política por `n_dias` e devolve as métricas médias diárias. Fonte…, ajustar_decay() (+11 more)

### Community 44 - "test_fems_dataset_integridade.py"
Cohesion: 0.13
Nodes (8): fems(), fixture, Integridade do dataset FEMS versionado em dados/fems_faz_002 (fonte padrão).…, O padrão do projeto agora é a cópia versionada (offline)., Σ(cargas) e Σ(geração) do loader devem bater com consumo_fatura., test_ambiente_roda_um_dia_sem_violacoes_estruturais(), test_balanco_energetico_bate_com_fatura(), test_config_aponta_para_dataset_versionado()

### Community 49 - "salvar_run"
Cohesion: 0.22
Nodes (9): Salva as 3 Q-tables do treino atual. Sem `dir_path`, grava um run versionado em…, save_qtables(), definir_label(), novo_run_id(), Define o rótulo manual (string livre) de um run., Gera um run_id por timestamp (ordenável lexicograficamente)., Persiste um treino completo em ``outputs/runs/<run_id>/``. Args: agentes : dict…, salvar_run() (+1 more)

### Community 50 - "_err"
Cohesion: 0.09
Nodes (22): Exception, configure_reward_weights(), _err(), evaluate_agents(), evaluate_split_test(), export_all_data(), get_actions(), get_financeiro_state() (+14 more)

### Community 51 - "cobertura_estados"
Cohesion: 0.50
Nodes (4): cobertura_estados(), Fração do espaço de estados discretos visitada no treino (bloco T2). Estados…, A cobertura deve ser reportável e estar em (0, 1]. O valor em si é o dado que…, test_cobertura_estados_reportada()

### Community 52 - "train_agents"
Cohesion: 0.25
Nodes (8): _congelar_politica(), _pesos_sao_default(), Congela a política IQL atual (cópia das Q-tables) sob um nome. O braço 'RL…, Copia as Q-tables atuais do IQL sob `nome` em state.snapshots., True se nenhum peso do reward foi alterado (o LLM-juiz ainda não agiu)., Treina os 3 agentes IQL com reward cooperativo. Dias percorridos…, snapshot_policy(), train_agents()

### Community 54 - "llm_policy.py"
Cohesion: 0.20
Nodes (9): criar_decisor_anthropic(), decisor_heuristico_simulado(), decisor_stub(), _estado_para_texto(), Política de controle baseada em LLM (braço "com MCP" do benchmark). Substitui…, Decisor offline determinístico (testes/validação sem custo de API). Por padrão…, Decisor que imita o heurístico — útil para checar o caminho 'válido' da…, Serializa o estado contínuo (rico) para o prompt do LLM. (+1 more)

### Community 55 - "auditar_base.py"
Cohesion: 0.47
Nodes (5): _abas(), _fmt(), main(), Auditoria de fidelidade à base v8 (itens 1 e 4 do plano de verificações). Fonte…, OK se |atual-base|/base <= tol; senão marca a divergência.

### Community 56 - "mcp_server.py"
Cohesion: 0.20
Nodes (9): construir_servidor(), definir_estado(), Servidor MCP que expõe o ambiente de energia como ferramentas (braço "LLM-via-…, Publica o estado da hora corrente para a tool ``estado_atual``., Devolve a última decisão registrada pelo LLM via ``decidir_controle``., Valida e registra uma decisão (compartilhado pela tool MCP)., Constrói o servidor FastMCP com as duas tools (import tardio do SDK)., _registrar_decisao() (+1 more)

### Community 57 - "SemAgente"
Cohesion: 0.29
Nodes (4): Roda o baseline heurístico em `n_dias` (ver `avaliar_politica`)., Cenário sem gestão nenhuma — a fazenda 'como está hoje'. Sem otimização: a…, Roda o baseline sem gestão em `n_dias` (ver `avaliar_politica`)., SemAgente

### Community 58 - "ler_meta"
Cohesion: 0.29
Nodes (8): _card_meta(), alternar_favorito(), atualizar_meta(), definir_favorito(), ler_meta(), Mescla `campos` no meta.json do run e devolve o meta atualizado., Inverte o status de favorito do run., test_salvar_run_registra_versao_da_codificacao()

### Community 59 - "metricas_convergencia"
Cohesion: 0.33
Nodes (6): metricas_convergencia(), Mede a estabilização de uma série de treino (bloco T2 — convergência). Compara…, A função de convergência distingue série estável de série ainda em queda., T2.3: a curva de custo por episódio estabiliza ao fim do treino., test_metricas_convergencia_serie_curta_e_sintetica(), test_treino_converge()

### Community 60 - "main"
Cohesion: 0.50
Nodes (4): construir_artefatos(), main(), SmartEnergy MAS — Pipeline principal. Execução completa: 1. Carrega dados do…, Recarrega um run e monta RES_R + todas as figuras/dados do dashboard. Tudo que…

### Community 65 - "resumo_mes"
Cohesion: 0.29
Nodes (7): slow, Calcula métricas médias diárias para um mês de simulações. Args: historicos :…, resumo_mes(), Mesma semente → mesmo resultado de avaliação (determinismo)., test_reprodutibilidade_mesma_semente(), T2.2: se o RL não superar o acaso, há erro de formulação do problema., test_rl_supera_politica_aleatoria()

## Knowledge Gaps
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_state()` connect `get_state` to `FazendaEnergyEnv`, `ServerState`, `evaluation.py`, `_carregar_fems`, `carregar_run`, `mcp/server.py`, `test_tools.py`, `salvar_run`, `_err`, `experiments.py`, `train_agents`, `run_episode`, `get_analysis_status`, `health_report`?**
  _High betweenness centrality (0.138) - this node is a cross-community bridge._
- **Why does `MCPServerError` connect `dashboard/state.py` to `test_tools.py`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **Why does `FazendaEnergyEnv` connect `FazendaEnergyEnv` to `get_state`, `evaluation.py`, `tests/conftest.py`, `BatteryModel`, `test_metrics.py`, `test_environment.py`, `test_tools.py`, `test_constraints.py`, `test_env.py`, `experiments.py`, `MetricsTracker`, `test_agent.py`, `AgentesHeuristicos`, `construir_agentes`, `ServerState`, `_carregar_fems`, `rodar_rl_mes`, `mcp/server.py`, `test_fems_dataset_integridade.py`, `_err`, `train_agents`, `run_episode`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Are the 47 inferred relationships involving `FazendaEnergyEnv` (e.g. with `executar_seed()` and `avaliar_politica()`) actually correct?**
  _`FazendaEnergyEnv` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `get_state()` (e.g. with `RuntimeError` and `ServerState`) actually correct?**
  _`get_state()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `dashboard/state.py` be split into smaller, more focused modules?**
  _Cohesion score 0.05128205128205128 - nodes in this community are weakly interconnected._
- **Should `test_resultados.py` be split into smaller, more focused modules?**
  _Cohesion score 0.12121212121212122 - nodes in this community are weakly interconnected._