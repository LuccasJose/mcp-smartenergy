---
label: Plano de reorganizacao
icon: tasklist
order: 68
---

# Reorganizacao incremental

## Limpeza documental (21/09/2026)

Escopo aprovado pelo mantenedor: remover os dois rascunhos academicos de
arquitetura, a PoC em notebook e todos os arquivos da pasta de relatos.
Foram preservados documentacao operacional, guia de apresentacao, fontes Word,
dados, modelos e resultados JSON. A refatoracao pendente dos agentes nao foi
revertida nem misturada com alteracoes de comportamento.

Removidos da arvore ativa: `docs/arquitetura-agentes-dissertacao.md`,
`docs/arquitetura-dissertacao-compilado.md`, `notebooks/smartenergy_mas_poc.ipynb`
e nove relatos Markdown, alem do marcador da pasta. Os arquivos versionados
podem ser consultados no commit `0e51402`, anterior a esta limpeza.
O relato de integridade de 07/09 nunca commitado tambem foi incluido em um
backup local fora do repositorio, junto com os demais arquivos removidos:
13 entradas, todas verificadas por SHA-256 antes das exclusoes.

Terminologia dos agentes, separacao entre orquestrador/ambiente/juiz e leituras
conceituais foram consolidadas em [Arquitetura](arquitetura.md). Nao foram
transplantadas como fatos atuais as antigas contagens de estados/acoes/tools,
garantias de seguranca ou ganhos experimentais. Referencias aos resultados
historicos apontam agora aos artefatos JSON preservados. Os registros abaixo
descrevem decisoes de suas respectivas datas, nao a existencia atual de cada arquivo.

## Extracao dos agentes (21/09/2026)

Escopo autorizado apos o commit `0e51402`: separar responsabilidades de
`smarty_energy.agents` sem alterar algoritmo, politica, dados, formato de runs,
selecao de checkpoint ou SoC. Configuracao global, modularizacao do servidor,
limpeza de documentos/notebooks e validacao cientifica ficam fora desta etapa.

**ADR-006: pacote de agentes com fachada publica compativel.** O antigo modulo
de 525 linhas passa a ser um pacote: `q_learning.py` para algoritmo/topologia,
`rules.py` para regras financeiras e baselines, `evaluation.py` para o laco
compartilhado e `system.py` para `IQLSystem`. O `__init__.py` reexporta os sete
simbolos publicos, sem exigir mudancas nos consumidores existentes.

Criterios de aceitacao: assinaturas e imports publicos preservados; Q-tables,
historicos e metricas iguais sob as mesmas seeds/dados sinteticos; arquivos
legados carregaveis; ausencia de ciclos de importacao em processos novos;
contratos arquiteturais validos, inclusive contra imports proibidos nos novos
submodulos. Testes do agente, baselines e runs executados antes e depois da
extracao. Os testes dos agentes e baselines passam a integrar o gate sintetico.

A extracao mecanica comparou os corpos por AST, ajustando apenas imports
relativos. A comparacao executada contra o codigo de `HEAD:src/smarty_energy/agents.py`
em `0e51402` confirmou sete assinaturas e paridade exata em tres seeds
(11, 29, 47), com tres episodios e seis dias sinteticos: Q-tables, historico
(exceto duracao) e metricas greedy iguais, incluindo ambas as baselines.
Nao e uma medicao de desempenho cientifico ou uma prova para todos os estados.

Corrigidas apenas as descricoes do IQL que chamavam a selecao legada de
holdout e o horizonte completo de early stopping; o comportamento foi preservado
e caracterizado em teste. Nao se deve confundir essa correcao textual com uma
mudanca de protocolo experimental. Veja [Componentes](componentes.md).

Verificacao local em 21/09/2026: **307 testes passaram em 74,82 s**, com oito
avisos conhecidos de depreciacao do cliente HTTP. Selecao sintetica explicita
do gate, incluindo agentes/baselines, bateria, ambiente, runs, divisoes, MCP
e transportes; nao foi a suite inteira. Quatro contratos arquiteturais aceitos
e violacoes deliberadas dos submodulos rejeitadas. Nenhum dataset real, treino
longo, juiz LLM ou chamada paga foi usado. CI remota nao foi verificada.

## Encerramento local

**Engenharia local concluida no escopo acordado em 20/09/2026.** O mantenedor
confirmou o encerramento dessa entrega e a separacao da validacao cientifica/
experimental, mantendo a documentacao apenas local, sem deploy. Esta decisao
nao certifica integralmente as premissas academicas do plano original.

Entregue: especificacoes de dominio e tecnica do recorte, matriz de regras e
evidencias, ADRs, startup explicito, ServerState, quatro contratos de imports,
testes sinteticos de fisica/persistencia/dados/MCP, transporte stdio/HTTP,
build documental reproduzivel e validacao local de HTML. Nao houve reescrita
da fisica nem separacao de CONFIG por cliente.

Aceite consolidado: **185 testes passaram em 22,97 s**, com oito avisos
conhecidos da API HTTP depreciada; **4 contratos de imports preservados**;
build de **15 paginas, zero erros e avisos**; **16 HTML** com links e ancoras
locais validos. Cobertura no recorte de oito modulos: **69,88% dos ramos**,
nao do repositorio inteiro; nao foi estabelecido limiar de 90% como gate.

Revisao de integracao posterior ao aceite: dois achados P2 foram corrigidos
com regressoes. Selecao atual: **187 testes Python passaram em 22,73 s** e
**13 testes Node passaram**, incluindo builds invalidos rejeitados. Os numeros
de cobertura acima pertencem ao aceite original; nao foram recalculados nesta
rodada. Oito avisos conhecidos do cliente HTTP continuam visiveis.

As tres paginas centrais foram verificadas em 320, 390 e 1280 px, sem excesso
horizontal apos ajustes do cabecalho e quebra de codigo inline. CLI e 41 tools
permanecem; scripts internos migram para initialize/get_state conforme os ADRs.
O mantenedor autorizou a integracao em seis commits e o push somente da branch
`refactor/reorganizacao-contratos`, incluindo o kit anterior e os quatro
artefatos Graphify revisados. Nao foi autorizado merge em main nem deploy.
Naquela entrega, o relato de integridade de 07/09 ficou fora dos commits.
Sua remocao posterior e a preservacao em backup estao registradas na secao
de limpeza documental acima.

Ordem aprovada: kit/dependencias; testes do motor; refatoracao MCP; documentacao
e build; contratos arquiteturais/CI; indice Graphify. A separacao parcial de
`pyproject.toml` e `tests/mcp/test_fisica_unificada.py` preserva essa ordem sem
modificar o working tree. O estado efetivo do envio deve ser confirmado pelas
referencias Git; este registro de autorizacao nao declara a CI remota aprovada.

**Fora deste aceite:** fontes e resultados cientificos, ensaios com dados reais,
metricas comparativas de manutencao antes/depois, autenticacao/concorrencia de
producao, UI Streamlit completa, CI remota e dominio publico. Limites do codigo
estao documentados, nao corrigidos silenciosamente nem considerados aprovados.
Esses itens requerem novo escopo e, quando aplicavel, autorizacao de execucao.

## Historico da entrega

As secoes cronologicas abaixo preservam os resultados e limitacoes de cada
incremento. Expressoes como "ainda nao executado" se referem a data/etapa
registrada; para o estado atual consulte o encerramento acima e o aceite final.

Data: 20/09/2026. Base de produto: `8130f3f`.
Branch: `refactor/reorganizacao-contratos`.
Escopo desta entrega: piloto de bateria, estados/acoes, continuidade do SoC,
checagens de runs, dados e MCP, inicializacao explicita, estado encapsulado,
contratos de dependencias, transportes locais reais, build documental e cobertura medida.
O escopo foi encerrado como entrega local, sem certificar todo o produto.

## ADR-001: preservar comportamento antes de separar responsabilidades

Estado: aceita para o processo de reorganizacao, autorizado pelo mantenedor
em 20/09/2026. Nao aprova mudancas de fisica, reward ou protocolo experimental.

Contexto original: documentacao e codigo divergiam em acoes de armazenamento,
throughput e secador. O MCP inicializava dados e estado global ao importar. Mover arquivos
sem contratos dificultaria distinguir refatoracao de alteracao de resultados.

Alternativas: reescrita integral; reorganizacao apenas de pastas; migracao por
contratos. Escolha: migracao incremental, apoiada por testes de caracterizacao
e invariantes, com visoes de dominio e tecnica ligadas por IDs estaveis.

Consequencias: APIs, formatos e regras atuais ficam preservados neste lote;
inconsistencias conhecidas entram no backlog, nao viram regras desejadas por
serem observadas. Cada lote deve ter comparacao antes/depois e revisao propria.
Se a decisao mudar, manter este registro como substituido e ligar o sucessor.

## ADR-002: inicializacao explicita do MCP

Estado: aceita para este incremento da reorganizacao autorizada em 20/09/2026.
Complementa ADR-001; nao aprova isolamento por cliente ou mudancas de fisica.

Problema: importar o modulo carregava a fonte de dados e criava objetos de
execucao, obrigando testes a interceptar o loader antes da importacao.
O teste `test_importacao_nao_carrega_dataset` reproduziu essa dependencia.

Alternativas: continuar com importacao ativa; inicializar implicitamente na
primeira tool; tornar o startup explicito; migrar todo o estado para objetos
de sessao de uma vez. Escolha: `initialize(loader=None)` explicito e idempotente,
chamado por `main` antes de HTTP/stdio. O loader opcional injeta dados para
testes; o padrao continua usando `carregar_dados` do motor.

Preparacao ocorre em variaveis locais antes de publicar dados, metadados,
agentes, tracker e ambiente. Falha de carga/construcao nao publica esses
objetos e permite nova tentativa. Inicializar novamente nao recarrega dados
nem apaga politicas. Troca de dataset continua sendo uma operacao separada.

Consequencias: CLI, nomes/assinaturas das tools, JSON e runs preservados;
chamadores Python que importavam e acessavam o estado devem chamar
`initialize()` primeiro. As quatro fixtures desse tipo foram migradas.
O modulo ainda registra tools e importa configuracao, inclusive leitura de
ambiente por config. Nao se promete importacao totalmente sem efeitos.

Limite daquele incremento: estado ativo e CONFIG permaneceram globais e
compartilhados por processo. A distribuicao em globais foi substituida por
ADR-003, sem duplicar representacoes. As limitacoes de concorrencia e
configuracao permanecem: nao ha lock nem initialize concorrente suportado.

Criterios de aceitacao deste incremento: importar sem chamar loader;
inicializar antes de transporte; nao executar transporte se a carga falhar;
permitir nova tentativa apos falha de construcao; preservar estado na chamada
repetida; manter contratos de tools, experimentos e igualdade com o pipeline.
Todos foram exercitados com dados sinteticos e transporte simulado.

## ADR-003: estado operacional unico

Estado: aceita para o encapsulamento autorizado em 20/09/2026. Complementa
ADR-002 e substitui somente sua representacao do estado em globais separados.

Problema: dados, ambiente, agentes, tracker, traces e referencias de runs
estavam distribuidos pelo modulo, exigindo declaracoes global nas operacoes.
Alternativas: manter os globais; introduzir objeto com aliases antigos; migrar
leituras e escritas para um unico objeto. Escolha: `ServerState` no modulo
mcp/state.py (`src/smarty_energy/mcp/state.py`), publicado por initialize
na referencia `_state`, com acesso por `get_state()`.

O objeto agrupa dados, tarifa, metadados, agentes, tracker, ambiente, dia ativo,
traces de SoC, snapshots e referencias de run/experimento. Ele nao implementa
fisica nem carrega dados. Seus componentes continuam sendo os do motor.
`snapshots` usa fabrica de dicionario por instancia; componentes fornecidos
ao construtor nao sao copiados. Nao e isolamento automatico entre instancias.

As tools capturam `state = get_state()` e operam nos campos correspondentes.
Nao ha aliases de compatibilidade para `DIAS`, `env`, `iql` e demais globais
antigos: scripts Python internos precisam migrar para os campos do objeto.
Nao ha setters de estado, proxies, copia de CONFIG ou mudanca de JSON/CLI.
`get_state` antes de initialize levanta RuntimeError com orientacao explicita.
Ambas sao APIs Python internas, nao tools expostas a clientes MCP.

Consequencias: uma referencia ativa por processo ainda e compartilhada entre
clientes; CONFIG permanece global no motor. Reset e switch_dataset atualizam
campos do mesmo objeto, na ordem anterior. Encapsulamento nao fornece lock,
rollback, imutabilidade, validacao de esquema nem sessao por cliente.
Regras fisicas, reward, codificacao, propagacao de SoC e arquivos de runs nao mudam.

Criterios: importacao sem dados; estado unico sem aliases antigos; inicializacao
completa/idempotente; identidade preservada em reset e troca; traces separados
para politica ativa e snapshot; 41 tools com assinaturas/decoradores preservados;
paridade com pipeline e roundtrips existentes aprovados. Evidencias abaixo.

## ADR-004: contratos de dependencias executaveis

Estado: aceita no incremento autorizado em 20/09/2026. Complementa ADR-003,
sem alterar regras fisicas, assinaturas MCP ou formatos de runs.

Contexto: grafo e revisao local confirmaram direcoes entre motor, backend MCP,
estado/auxiliares e clientes. O indice auxilia a navegacao, mas nao impede
introduzir dependencias inversas. Alternativas: revisao manual apenas, linter
caseiro ou Import Linter. Escolha: Import Linter 2.15 (Grimp 3.17 instalado)
com quatro contratos forbidden no `pyproject.toml`.

Regras A-DEP-001 a A-DEP-004 e escopo detalhados na
[especificacao tecnica](arquitetura.md). Imports internos diretos/indiretos
sao verificados; sem ignore_imports e sem allow_indirect_imports. Nao se
impoe uma hierarquia completa nem ausencia de ciclos em todo o motor.

Descoberta: a primeira execucao falhou porque dashboard nao era reconhecido.
Foram adicionados marcadores `__init__.py` sem imports a dashboard e pages,
para que as paginas tambem sejam analisadas. Nao se descartou o contrato.
O codigo instalado do Streamlit 1.64.0 em `_mpa_v1` exclui explicitamente
`__init__.py` da lista de paginas. UI real nao foi executada nesta etapa.

Criterios: quatro contratos aprovados no produto; oito violacoes deliberadas
(direta e indireta por contrato) rejeitadas em copias temporarias; teste
positivo com sentinela que falharia se o analisador executasse o pacote;
gate dedicado de imports na CI e testes incluidos na selecao sintetica.

Limites: listas do motor/backend sao explicitas e exigem manutencao; novos
subdiretorios sem marcador de pacote podem ficar fora do grafo. Imports
dinamicos, dependencias externas, efeitos de __init__ ancestrais e fluxo por
objetos nao sao garantidos. O pacote raiz ainda reexporta visualizacao e motor;
essa limitacao nao foi escondida nem refatorada como parte deste gate.

## Etapas e saidas

ADR-005 (20/09/2026): documentacao gerada permanece restrita a docs/, sem
copiar codigo, grafo, notas ou configuracoes externas para o site. Links entre
paginas sao mantidos; referencias a arquivos fora de docs/ passam a indicar
o caminho no repositorio em texto. Alternativas rejeitadas neste lote: ampliar
o input para a raiz ou apontar para arquivos ainda nao publicados no GitHub.
Tradeoff: essas referencias deixam de ser hyperlinks no Markdown, mas mantem
rotulo, caminho e IDs de regras/testes. A navegacao de codigo continua no clone.

| Etapa | Saida e criterio para avancar | Estado |
|---|---|---|
| 1. Piloto e linha de base | Regras do piloto, fontes, testes sinteticos e lacunas explicitas; nenhum modulo de produto modificado. | Entregue no escopo do piloto |
| 2. Protecao ampliada | Cobertura de ramos medida; selecao offline explicita; contratos de MCP, dados e runs exercitados. | Recorte entregue: roundtrip, fontes, reset, JSON e stdio/HTTP sinteticos; atomicidade e validacao completa pendentes |
| 3. Limites arquiteturais | ADR de dependencias aprovado; contratos de imports automatizados; inicializacao MCP explicita sem quebrar clientes. | Entregue localmente: ADR-002/003/004, estado e contratos; SDK/cliente Python dashboard testados no transporte; UI, clientes externos e CI remota pendentes |
| 4. Migracao por lotes | Configuracao e responsabilidades separadas onde os testes justificarem; resultados equivalentes nos cenarios aprovados. | Encerrada no recorte local: startup e estado MCP migrados, paridade sintetica protegida; configuracao por cliente e novas refatoracoes ficam para outro escopo |
| 5. Rotina e reproducao | Gates de documentacao/testes, dependencias reproduziveis e evidencias experimentais rastreaveis. | Aceite local concluido: build/links e gates executados; CI remota, fontes cientificas e reproducao experimental fora deste aceite |

## Matriz do piloto

A [visao de dominio](regras-dominio.md) e a
[visao tecnica](arquitetura.md) usam os mesmos identificadores.
Os testes abaixo caracterizam o escopo indicado, nao todas as combinacoes do sistema.

| Regra | Implementacao | Evidencia executavel |
|---|---|---|
| R-BAT-001 | BatteryModel.charge/discharge (`src/smarty_energy/battery.py`) | test_battery.py (`tests/test_battery.py`): `test_carga_respeita_eficiencia_e_origem`, `test_descarga_respeita_eficiencia_e_limite_minimo`; propriedades (`tests/test_battery_properties.py`): conservacao AC/DC |
| R-BAT-002 | BatteryModel (`src/smarty_energy/battery.py`) | test_battery.py (`tests/test_battery.py`): limites e bloqueios; propriedades (`tests/test_battery_properties.py`): `test_sequences_preserve_soc_and_share_dc_throughput` |
| R-BAT-003 | BatteryModel.reset (`src/smarty_energy/battery.py`), FazendaEnergyEnv.reset (`src/smarty_energy/environment.py`) | test_battery.py (`tests/test_battery.py`): `test_reset_preserva_soc_informado_e_renova_throughput`; test_environment.py (`tests/test_environment.py`): `test_env_reset_preserva_soc_e_reinicia_contadores` |
| R-ACO-001 | config (`src/smarty_energy/config.py`), FazendaEnergyEnv.step (`src/smarty_energy/environment.py`) | test_environment.py (`tests/test_environment.py`): `test_env_contrato_estados_e_acoes`, `test_env_carga_rede_limiar_tarifario`, `test_env_carga_rede_prioriza_excedente`; nao certifica o balanco ao saturar PCC |
| R-EST-001 | FazendaEnergyEnv.discretizar (`src/smarty_energy/environment.py`) | test_environment.py (`tests/test_environment.py`): `test_env_discretizacao_limites`, `test_env_discretizacao_meta_secador`, `test_env_contrato_estados_e_acoes` |
| R-SOC-001 | evaluation (`src/smarty_energy/evaluation.py`), training.treinar (`src/smarty_energy/training.py`) | test_environment.py (`tests/test_environment.py`): `test_avaliacao_mensal_encadeia_soc_na_ordem`, `test_avaliacao_mensal_publica_preserva_argumentos`, `test_avaliacao_mensal_publica_integra_bateria`; test_training.py (`tests/test_training.py`): `test_treino_curto_propaga_soc` |
| R-TRE-001 | training.treinar (`src/smarty_energy/training.py`) | test_training.py (`tests/test_training.py`): `test_treino_completa_horizonte_e_restaura_checkpoint`; horizonte de tres episodios e custo de avaliacao controlado, sem afirmar qualidade de RL |
| R-RUN-001 | runs.verificar_compatibilidade (`src/smarty_energy/runs.py`) | test_runs.py (`tests/test_runs.py`): versao, dimensao/faixa de chave e avisos de fisica/configuracao ausente |
| R-RUN-002 | runs (`src/smarty_energy/runs.py`), AgenteQL.load (`src/smarty_energy/agents.py`), MCP (`src/smarty_energy/mcp/server.py`) | test_runs.py (`tests/test_runs.py`): roundtrip, run ausente e numero de acoes; test_tools.py (`tests/mcp/test_tools.py`): roundtrip pipeline/MCP e bloqueio de save sem historico |
| R-DAD-001 | data_loader (`src/smarty_energy/data_loader.py`) | test_data_loader_fems.py (`tests/test_data_loader_fems.py`): prioridade sem fallback, retorno, metadados e FEMS temporario; nao valida leitura real de Excel/Sheets |
| R-MCP-001 | switch_dataset / step_environment (`src/smarty_energy/mcp/server.py`) | test_switch_dataset.py (`tests/mcp/test_switch_dataset.py`): reset e falha de leitura; test_tools.py (`tests/mcp/test_tools.py`): indices invalidos, equivalencia com motor e booleanos JSON |
| R-MCP-002 | initialize / main (`src/smarty_energy/mcp/server.py`) | test_tools.py (`tests/mcp/test_tools.py`): importacao sem dados, loader injetado, falha/nova tentativa, idempotencia e ordem do transporte; ADR-002 |
| R-MCP-003 | ServerState (`src/smarty_energy/mcp/state.py`), get_state / tools (`src/smarty_energy/mcp/server.py`) | test_tools.py (`tests/mcp/test_tools.py`): estado unico, erro antes de initialize, snapshots independentes por padrao, identidade em reset e traces separados; test_switch_dataset.py (`tests/mcp/test_switch_dataset.py`): identidade na troca e falha de leitura; ADR-003 |
| R-MCP-004 | main / tools (`src/smarty_energy/mcp/server.py`), cliente dashboard (`src/smarty_energy/mcp/dashboard/mcp_client.py`) | test_transport.py (`tests/mcp/test_transport.py`): stdio/HTTP reais, handshake, catalogo, estado, erros, cliente sincrono e encerramento; escopo completo em [MCP](mcp.md) |
| A-DEP-001 a A-DEP-004 | Contratos Import Linter (`pyproject.toml`), gate CI (`.github/workflows/qualidade-kit.yml`) | test_fisica_unificada.py (`tests/mcp/test_fisica_unificada.py`): codigo atual aceito sem executar; oito violacoes diretas/indiretas rejeitadas; ADR-004 |

## Verificacao local do piloto

Use a `.venv` do projeto. No PowerShell, a partir da raiz:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
& .\.venv\Scripts\python.exe -m coverage run -m pytest tests/test_battery.py tests/test_battery_properties.py tests/test_docs.py tests/test_environment.py tests/test_runs.py tests/test_data_loader_fems.py tests/mcp/test_tools.py tests/mcp/test_switch_dataset.py tests/mcp/test_experiments.py tests/mcp/test_fisica_unificada.py tests/mcp/test_transport.py tests/test_training.py::test_treino_curto_propaga_soc tests/test_training.py::test_treino_completa_horizonte_e_restaura_checkpoint -q
& .\.venv\Scripts\python.exe -m coverage report
& .\.venv\Scripts\python.exe -m coverage json
& .\.venv\Scripts\python.exe -m ruff check .
```

A selecao usa dados sinteticos, seed 42 da fixture compartilhada, tres episodios
no teste de continuidade, chamadas de dois episodios nos testes MCP e exemplos
deterministas do Hypothesis. Usa arquivos Parquet e runs em tmp_path. Nao carrega
datasets privados, nao baixa dados, nao chama LLM e nao grava runs de produto.
O teste de continuidade desliga selecao greedy; o teste de checkpoint usa
avaliacoes de custo controladas. Nenhum valida convergencia nem qualidade.
As fixtures MCP inicializam explicitamente com loader sintetico. Testes de
startup unitarios substituem `mcp.run`; testes de experimentos usam tmp_path e testes
de paridade semeiam Q-tables com RNG local de seed 7, sem treinar.
O gate de imports e executado separadamente, conforme o
[guia do kit](kit-agentes.md); os testes negativos ja fazem parte da selecao
acima e alteram somente copias temporarias de codigo/configuracao.
Os dois testes de transporte iniciam processos reais, sem treino, com stdio
e HTTP loopback. Nao exigem servidor previo, porta fixa ou credenciais e
encerram os processos no final. Nao se mede cobertura dentro desses filhos.

Resultados historicos do lote inicial em 20/09/2026, Python 3.14.7 na `.venv`
do projeto, antes da ampliacao de testes e da instalacao de coverage.py:

- Selecao inicial: **72 testes passaram em 1,80 s**, tempo reportado pelo
   pytest. Nao e uma medicao de CI nem de treinamento representativo.
- `python -m ruff check .`: passou.
- `python -m pre_commit run --files` nos arquivos do lote: Ruff, conflitos e
   YAML passaram; TOML foi ignorado por nao haver arquivo aplicavel.
- Diagnosticos do editor: sem erros nos quatro arquivos de teste e no workflow.
- Destinos dos links Markdown locais dos sete documentos do piloto: existentes.
   Nao valida ancoras nem a renderizacao do site.
- `graphify update .` e `graphify diagnose multigraph`: 981 nos e 1716 arestas,
   sem endpoints ausentes ou duplicatas exatas no grafo final. Sem extracao por LLM.

A CI foi configurada para essa selecao em Python 3.12, mas nao foi executada
remotamente. O build Retype nao foi executado: Node/npm nao estao no PATH.
Cobertura de ramos, suite completa e experimentos nao foram executados.
Nenhuma dependencia foi instalada, nem houve commit ou push neste lote.

## Ampliacao: contratos publicos e cobertura

Resultados locais de 20/09/2026, Python 3.14.7 e coverage.py 7.16.1:

- Cinco cenarios novos de carga pela rede: passaram (limiar estrito, vizinhos
   representaveis, prioridade do excedente e motivos de bloqueio).
- Dezesseis cenarios novos das funcoes mensais: passaram (quatro caminhos,
   padrao e opcoes explicitas, mais integracao RL/LLM de dois dias).
- Selecao instrumentada anterior (antes de dados/MCP): **93 testes passaram em 1,86 s**.
- Instalacao por `uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt`:
   somente coverage.py 7.16.1 foi adicionado. `uv pip check` aprovou 93 pacotes.
- Relatorio e JSON gerados localmente; `git check-ignore` confirmou que ambos
   os arquivos de dados `.coverage` e `.coverage-piloto.json` estao ignorados.
- `python -m ruff check .` e `python -m pre_commit run --files` nos arquivos
   desta etapa: passaram, incluindo as verificacoes de TOML e YAML.
- Diagnosticos do editor sem erros; destinos dos links locais dos quatro
   documentos atualizados existentes; `git diff --check` passou.
- Graphify atualizado: 985 nos e 1727 arestas; o diagnostico nao encontrou
   endpoints ausentes nem duplicatas exatas no grafo final.
- `git diff --exit-code -- src/` confirmou que o produto permaneceu inalterado.
   Branch mantida; sem commit ou push.

O escopo do relatorio nessa medicao era `[tool.coverage.report].include`: cinco modulos
inteiros, nao somente as funcoes testadas, e nao o repositorio inteiro.
Contagens extraidas do JSON com o parser `json` do Python:

| Modulo | Linhas executadas/total | Linhas (%) | Ramos executados/total | Ramos (%) |
|---|---|---|---|---|
| battery.py (`src/smarty_energy/battery.py`) | 63/63 | 100,00 | 12/12 | 100,00 |
| environment.py (`src/smarty_energy/environment.py`) | 192/196 | 97,96 | 36/38 | 94,74 |
| evaluation.py (`src/smarty_energy/evaluation.py`) | 53/99 | 53,54 | 10/28 | 35,71 |
| runs.py (`src/smarty_energy/runs.py`) | 71/157 | 45,22 | 14/46 | 30,43 |
| training.py (`src/smarty_energy/training.py`) | 67/107 | 62,62 | 15/32 | 46,88 |
| Total do recorte | 446/622 | 71,70 | 87/156 | 55,77 |

`coverage report` combina linhas e ramos e mostrou **68,51%** no total. Nao
confundir essa porcentagem com os **55,77% de ramos**. No PowerShell 5.1,
`ConvertFrom-Json` rejeitou esse relatorio; o parser `json` do Python o leu.
Cobertura mede execucao, nao forca das assercoes, conservacao em todos os casos
nem qualidade de politicas. Mesmo 100% na bateria nao comprova esses aspectos.

Nao foi imposto `fail_under`: esta e uma linha de base, nao a aprovacao de uma
meta global. A CI agora executa a selecao sob cobertura e imprime o relatorio,
mas continua nao executada remotamente. O motor nao foi alterado. Persistem as
limitacoes do build Retype e da suite completa; nenhum experimento foi rodado.

## Ampliacao: persistencia, dados e MCP

Em 20/09/2026, no mesmo Python 3.14.7 com coverage.py 7.16.1:

- `pytest tests/test_runs.py -q`: 13 passaram; roundtrip real de tabelas,
   historico, configuracao e epsilon, usando somente arquivos temporarios.
- `pytest tests/test_data_loader_fems.py -q`: 11 passaram; fontes externas
   substituidas nos testes de prioridade, FEMS sintetico nos testes de leitura.
- A primeira execucao MCP mostrou falha de JSON em passo valido. Reproducao:
   `pytest tests/mcp/test_tools.py::test_step_environment_preserva_contrato_do_motor -q --showlocals`;
   payload de erro: `TypeError: Object of type bool is not JSON serializable`.
- Correcao local: `step_environment` normaliza `numpy.bool_` para `bool`,
   preservando chaves, precisao e calculos. Caso isolado passou; os 31 testes
   MCP passaram antes de adicionar tambem o caso de tarifa no pico.
- Selecao anterior, incluindo pico e fora-pico: **141 testes passaram
   em 6,72 s**. `python -m ruff check .` passou; diagnosticos sem erros nos
   arquivos Python e configuracoes alterados.
- Hooks nos arquivos desta etapa: Ruff, conflitos, TOML e YAML passaram.
   Destinos dos links locais dos seis documentos atualizados existem;
   diagnosticos documentais sem erros. Isso nao substitui o build Retype.
- `graphify update .` e `graphify diagnose multigraph`: 999 nos, 1763 arestas,
   sem endpoints ausentes nem duplicatas exatas no grafo final.
- `git diff -- src/` confirmou somente a normalizacao de booleanos na tool
   `step_environment`. Branch preservada; sem commit ou push.

Nao se mudou reward, fisica ou formato de runs. A unica alteracao de produto
desta etapa esta na serializacao da resposta MCP. Nenhuma dependencia nova,
treino longo, dataset privado, chamada paga ou servidor HTTP foi utilizado.

O relatorio agora inclui sete modulos inteiros (acrescentados data_loader e
mcp/server). O total nao e diretamente comparavel ao antigo recorte de cinco.

| Modulo | Linhas executadas/total | Linhas (%) | Ramos executados/total | Ramos (%) |
|---|---|---|---|---|
| battery.py (`src/smarty_energy/battery.py`) | 63/63 | 100,00 | 12/12 | 100,00 |
| environment.py (`src/smarty_energy/environment.py`) | 195/196 | 99,49 | 37/38 | 97,37 |
| evaluation.py (`src/smarty_energy/evaluation.py`) | 60/99 | 60,61 | 11/28 | 39,29 |
| runs.py (`src/smarty_energy/runs.py`) | 85/157 | 54,14 | 19/46 | 41,30 |
| training.py (`src/smarty_energy/training.py`) | 76/107 | 71,03 | 20/32 | 62,50 |
| data_loader.py (`src/smarty_energy/data_loader.py`) | 63/100 | 63,00 | 10/14 | 71,43 |
| mcp/server.py (`src/smarty_energy/mcp/server.py`) | 391/574 | 68,12 | 85/148 | 57,43 |
| Total do recorte | 933/1296 | 71,99 | 194/318 | 61,01 |

O total combinado do `coverage report` e **69,83%**, distinto dos **61,01%
de ramos**. Porcentagens nao medem qualidade do modelo nem seguranca completa.

Limitacoes: tools chamadas diretamente, sem transporte/autenticacao; pickle
somente confiavel; carregar_run pode modificar agentes antes de uma falha;
troca de dataset nao tem rollback geral; tarifas FEMS supoem curva unica sem
filtrar fatura por fazenda/mes. Esses comportamentos nao foram redefinidos.
CI remota, build Retype e suite completa continuam nao executados.

## Inicializacao explicita: verificacao

Em 20/09/2026, Python 3.14.7 e coverage.py 7.16.1:

- Antes da mudanca, `pytest tests/mcp/test_tools.py::test_importacao_nao_carrega_dataset -q`
   falhou ao chamar o loader durante o import. Apos a mudanca passou.
- `pytest tests/mcp/test_tools.py tests/mcp/test_switch_dataset.py tests/mcp/test_experiments.py tests/mcp/test_fisica_unificada.py -q`:
   **53 testes passaram em 5,97 s**. Inclui retorno JSON, persistencia de
   experimentos e paridade de fisica e metricas com o pipeline.
- Selecao no incremento de startup, antes de ServerState: **162 testes passaram em 9,31 s**.
   `python -m ruff check .` passou; diagnosticos sem erros nos arquivos Python.
- Hooks dos arquivos alterados: Ruff, conflitos e YAML passaram; TOML sem
   arquivo aplicavel neste lote. Links locais dos cinco documentos validos,
   diagnosticos documentais sem erros e `git diff --check` aprovado.
- Graphify atualizado e diagnosticado: 1008 nos, 1785 arestas, sem endpoints
   ausentes ou duplicatas exatas no grafo final. Sem extracao por LLM.
- Nao houve mudanca de calculos, parametros fisicos, reward, estados/acoes,
   selecao de fonte ou formato de runs. Nao houve instalacao de dependencias.
   Branch mantida em `refactor/reorganizacao-contratos`, sem commit ou push.

Medicao historica dos mesmos sete modulos, antes de ServerState:

| Modulo | Linhas executadas/total | Linhas (%) | Ramos executados/total | Ramos (%) |
|---|---|---|---|---|
| battery.py (`src/smarty_energy/battery.py`) | 63/63 | 100,00 | 12/12 | 100,00 |
| environment.py (`src/smarty_energy/environment.py`) | 195/196 | 99,49 | 37/38 | 97,37 |
| evaluation.py (`src/smarty_energy/evaluation.py`) | 84/99 | 84,85 | 17/28 | 60,71 |
| runs.py (`src/smarty_energy/runs.py`) | 85/157 | 54,14 | 19/46 | 41,30 |
| training.py (`src/smarty_energy/training.py`) | 76/107 | 71,03 | 20/32 | 62,50 |
| data_loader.py (`src/smarty_energy/data_loader.py`) | 63/100 | 63,00 | 10/14 | 71,43 |
| mcp/server.py (`src/smarty_energy/mcp/server.py`) | 436/591 | 73,77 | 96/150 | 64,00 |
| Total do recorte | 1002/1313 | 76,31 | 211/320 | 65,94 |

O relatorio combinado mostrou 74,28%; nao e a porcentagem de ramos. Nao ha
limiar de aprovacao por cobertura. Transportes foram simulados; clientes reais,
CI remota, build Retype e suite completa nao foram executados. Estado continua
global e compartilhado naquele incremento, conforme ADR-002. Nao se declara concluida a etapa 3.

## Encapsulamento: verificacao

Em 20/09/2026, Python 3.14.7 e coverage.py 7.16.1:

- `test_estado_unico_concentra_objetos` falhou antes de implementar get_state
   e passou apos construir ServerState. A migracao mecanica usou AST e analise
   de escopo, preservando strings JSON e variaveis locais. Duas verificacoes
   dinamicas de atributos nos testes foram adaptadas ao novo objeto.
- Quatro conjuntos MCP passaram apos migracao; testes adicionais protegeram
   ausencia de aliases, identidade, dicionario de snapshots por instancia e
   cadeias distintas de SoC, sem aprendizado pelo snapshot em mode=train.
- Gate completo sob cobertura: **167 testes passaram em 10,98 s**.
- Comparacao AST com `HEAD` confirmou **41 tools** com os mesmos nomes,
   argumentos, anotacoes de retorno e decoradores. A unica declaracao global
   restante no servidor e `_state` em initialize. Isso nao prova identidade
   de todo comportamento nem substitui testes de payload e integracao.
- Segunda comparacao AST confirmou os corpos das 41 tools ao normalizar
   acessos ao estado, declaracoes global, docstrings e a conversao bool NumPy
   corrigida no lote anterior. Nao foi necessario mudar calculos ou payloads.
- `python -m ruff check .` e hooks de Ruff, conflitos e TOML passaram;
   YAML sem arquivo aplicavel neste lote. Diagnosticos sem erros nos arquivos
   alterados e links locais dos seis documentos com destinos existentes.
- `graphify update .` e diagnostico: 1019 nos, 1852 arestas, sem endpoints
   ausentes ou duplicatas exatas no grafo final. `git diff --check` passou.
   Branch preservada em `refactor/reorganizacao-contratos`.

O escopo de cobertura agora tem oito modulos inteiros, incluindo ServerState.
Resultado combinado do `coverage report`: **74,78%**. No JSON:

| Modulo | Linhas executadas/total | Linhas (%) | Ramos executados/total | Ramos (%) |
|---|---|---|---|---|
| battery.py (`src/smarty_energy/battery.py`) | 63/63 | 100,00 | 12/12 | 100,00 |
| environment.py (`src/smarty_energy/environment.py`) | 195/196 | 99,49 | 37/38 | 97,37 |
| evaluation.py (`src/smarty_energy/evaluation.py`) | 84/99 | 84,85 | 17/28 | 60,71 |
| runs.py (`src/smarty_energy/runs.py`) | 85/157 | 54,14 | 19/46 | 41,30 |
| training.py (`src/smarty_energy/training.py`) | 76/107 | 71,03 | 20/32 | 62,50 |
| data_loader.py (`src/smarty_energy/data_loader.py`) | 63/100 | 63,00 | 10/14 | 71,43 |
| mcp/server.py (`src/smarty_energy/mcp/server.py`) | 455/618 | 73,62 | 103/152 | 67,76 |
| mcp/state.py (`src/smarty_energy/mcp/state.py`) | 15/15 | 100,00 | 0/0 | Nao aplicavel |
| Total do recorte | 1036/1355 | 76,46 | 218/322 | 67,70 |

O total e do recorte de oito modulos, nao do repositorio inteiro. A classe de
estado nao possui ramos medidos; 100% de linhas nela nao comprova isolamento.
Nao houve nova dependencia, treino longo, dado privado, chamada paga, commit
ou push. Transporte real, CI remota, build Retype e suite completa permanecem
nao executados. Encapsulamento nao encerra a reorganizacao nem a etapa 3.

## Dependencias: verificacao

Em 20/09/2026, Python 3.14.7:

- Instalacao por requirements-dev: Import Linter 2.15, Grimp 3.17,
   markdown-it-py 4.2.0, mdurl 0.1.2 e Rich 15.0.0 adicionados.
   `uv pip check --python .venv/Scripts/python.exe --offline`: 98 pacotes compativeis.
- `lint-imports --config pyproject.toml --no-cache` com PYTHONPATH=src:
   **34 arquivos, 65 dependencias; 4 contratos preservados, 0 quebrados**.
- `pytest tests/mcp/test_fisica_unificada.py -k contratos_arquitetura -q`:
   **9 passaram em 5,71 s**, incluindo oito casos negativos isolados.
- Gate completo sob coverage.py: **176 testes passaram em 15,67 s**.
   O recorte continua com oito modulos: cobertura combinada de 74,78%,
   mesmas contagens de linhas/ramos da tabela de encapsulamento acima.
- Nao foram modificados os arquivos de servidor, estado, fisica ou calculos
   nesta etapa. Os dois marcadores de pacote do dashboard tem apenas docstrings.
   Alteracoes existentes nas fixtures e no servidor foram preservadas.
- `python -m ruff check .` e hooks nos arquivos alterados: Ruff, conflitos,
   TOML e YAML aprovados. Diagnosticos sem erros; destinos dos links locais
   dos quatro documentos atualizados existentes; `git diff --check` passou.
- Graphify atualizado e diagnosticado: 1028 nos, 1872 arestas, sem endpoints
   ausentes ou duplicatas exatas no grafo final. Nao houve extracao por LLM.

CI configurada, nao executada remotamente. Transporte real, UI, build Retype,
suite completa e experimentos longos nao executados. Branch preservada;
sem commit, push ou novo treinamento experimental.

## Transporte real: verificacao

Em 20/09/2026, Python 3.14.7, MCP 1.30.0, Uvicorn 0.53.0, HTTPX 0.28.1
e AnyIO 4.15.1, sem instalacao de novas dependencias:

- `pytest tests/mcp/test_transport.py -q`: **2 passaram em 8,64 s**.
- Gate completo daquele incremento, antes de test_docs: **178 passaram em 25,08 s**.
   Oito avisos de depreciacao do `streamablehttp_client` utilizado no cliente
   existente do dashboard, sem supressao nem mudanca de API nesta etapa.
- Ambos negociaram MCP e listaram 41 tools. Foram verificados schema requerido
   do passo, consulta de dados/observacao, indice e tipo invalidos, tool
   inexistente, passo valido, booleanos, continuidade de hora, reset e ping.
- HTTP tambem exercitou `mcp_client.call_tool` e `ping` reais, incluindo
   `MCPServerError` e persistencia do estado entre sessoes novas por chamada.
- O loader padrao foi substituido por falha deliberada no filho; initialize
   recebeu somente JSON gerado das fixtures sinteticas. Ambiente-base do SDK
   mais variaveis explicitas, `.env` desabilitado e cwd temporario.
- Stdio usou subprocesso gerenciado pelo SDK. HTTP usou Uvicorn real e porta
   efemera em 127.0.0.1, com sinal de prontidao e parada por stdin no harness.
   Encerramento normal confirmado por marcador; HTTP tambem exigiu exit code 0
   e thread de leitura encerrada. Nenhum servidor permaneceu ativo.
- `coverage report`: 74,78% combinado no mesmo recorte de oito modulos,
   contagens anteriores preservadas. Servidores filhos nao foram instrumentados:
   esses testes demonstram contratos pelo protocolo, nao aumento de cobertura.
- `python -m ruff check .` e hooks: Ruff, conflitos e YAML passaram; TOML
   sem arquivo aplicavel nesta etapa. Diagnosticos sem erros, links locais dos
   quatro documentos com destinos existentes e `git diff --check` aprovado.
- Graphify atualizado e diagnosticado: 1039 nos, 1886 arestas, sem endpoints
   ausentes ou duplicatas exatas no grafo final. Sem extracao semantica/LLM.
   Branch mantida em `refactor/reorganizacao-contratos`.

Somente testes, workflow e documentacao foram alterados nesta etapa. Nao houve
mudanca de produto, regra fisica, reward, assinaturas, formato de runs ou fonte.
Fontes oficiais do SDK e implementacao instalada foram conferidas para o
ciclo de transporte; o harness observa startup de Uvicorn sem substituir rotas.

Limites: nao executa UI Streamlit, VS Code/Claude, auth, TLS, proxy remoto,
concorrencia, testes de carga, todas as tools ou queda forcada do servidor.
Nao prova seguranca de deployment. CI remota, build Retype, suite completa e
experimentos longos continuam nao executados. Sem commit ou push.

## Documentacao: verificacao

Em 20/09/2026, Node portatil 22.23.2, npm 10.9.8 e Retype 4.6.0:

- Download oficial de Node com SHA256 conferido; sem admin/PATH global.
   `npm --prefix docs ci --no-audit --no-fund` instalou dois pacotes do lockfile
   existente, sem atualizar dependencias. `.venv` nao foi alterada neste lote.
- O primeiro npm run falhou por ausencia do atalho retype. Os scripts passaram
   a invocar diretamente `node node_modules/retypeapp/retype.js`.
- O primeiro build completo teve 15 paginas, zero erros e 194 avisos:
   97 referencias externas a docs/ foram avisadas duas vezes. A conversao
   mecanica usou parser Markdown para preservar blocos de codigo e links do site.
- Build limpo: **15 paginas, zero erros e zero avisos**. Sao 16 arquivos HTML
   incluindo a pagina 404. `python scripts/verificar_docs.py` aprovou destinos
   href/src e ancoras locais; nao verifica URLs externas nem referencias em CSS.
- `pytest tests/test_docs.py -q`: **6 testes passaram em 0,42 s**, incluindo
   HTML valido, recurso ausente, ancora ausente e escape do diretorio do site.
- Navegacao em navegador local por arquivo: inicio -> regras de dominio ->
   arquitetura funcionou; H1 visivel em desktop 1280x800 e mobile 390x844.
   Medicao mobile encontrou scrollWidth 397 para viewport 390: pequeno overflow
   de tema/conteudo ainda pendente, nao se declara auditoria visual completa.
- Navegacao usa index.html explicito e busca pre-carregada. O logo e metadados
   ainda usam a URL de exemplo original, pois Retype exige uma base aceita.
   Publicacao requer URL real; CNAME desativado. Nenhum site foi publicado.
- Job documental adicionado a CI: Node fixado, npm ci, build e checagem HTML;
   testes do verificador incluidos no gate Python. CI remota nao executada.
- Verificacao focada final: `pytest tests/test_docs.py tests/test_battery.py tests/test_battery_properties.py -q`
   aprovou **19 testes em 1,24 s**. Ruff, hooks aplicaveis, diagnosticos e
   `git diff --check` passaram. A selecao completa Python nao foi reexecutada
   neste lote documental; seus ultimos resultados permanecem historicos.
- Lockfile sem diff; CNAME e metadados npm ausentes da saida limpa. Graphify
   atualizado e diagnosticado: 1054 nos, 1907 arestas, sem endpoints ausentes
   nem duplicatas exatas no grafo final. Documentacao nao foi indexada no grafo.
   Branch preservada, sem commit, push, deploy ou servidor persistente.

`docs/.gitignore` ja protegia node_modules, site, .retype e manifest. O build
agora substitui a saida gerada para nao deixar artefatos de builds anteriores.
Motor, testes de protocolo e regras fisicas nao foram alterados. O build
valida geracao/navegacao, nao a fundamentacao cientifica ou atualidade de cada
afirmacao das paginas historicas. Comandos completos no [guia do kit](kit-agentes.md).

## Aceite final de engenharia

Verificacao de 20/09/2026 na `.venv` Python 3.14.7, com .env desabilitado:

- Comando consolidado acima: **185 passaram em 22,97 s**; oito avisos de
   depreciacao de `streamablehttp_client` permanecem visiveis e registrados.
- Novo teste R-TRE-001: os tres episodios sao executados mesmo quando o custo
   greedy piora; as Q-tables do melhor checkpoint sao restauradas ao final.
   As metricas de treino nao sao resultados cientificos de desempenho.
- Import Linter: **34 arquivos, 65 dependencias, quatro contratos satisfeitos**.
- `coverage report`: **75,91% combinado**. JSON: **1048/1355 linhas (77,34%)**,
   **225/322 ramos (69,88%)**. O processo filho dos testes MCP nao e instrumentado.
   Coverage e evidencia auxiliar, nao garantia de ausencia de bugs.
- Correcao mobile: badge opcional removido; `docs/_includes/head.html`
   permite quebra de codigo inline e marca em duas linhas em telas estreitas,
   preservando blocos pre, tabelas e controles. Nao houve recorte global de pagina.
- Navegador: arquitetura, regras de dominio e plano em 320/390/1280 px,
   com largura util = scrollWidth em todos os nove casos (305/375/1265 px).
   Conferencia de screenshots complementa as medicoes, sem certificar acessibilidade completa.
- Descricoes de treino/baseline e nomes de paginas MCP reconciliados com
   codigo atual; artigos e resultados historicos nao receberam nova validacao.
- Build final Retype: **15 paginas, zero erros e zero avisos**;
   `scripts/verificar_docs.py` aprovou 16 arquivos HTML com destinos e ancoras
   locais. Ruff, hooks aplicaveis, diagnosticos e `git diff --check` passaram.
- Graphify atualizado e diagnosticado: **1055 nos, 1909 arestas**, sem
   endpoints ausentes nem duplicatas exatas no grafo final. Nao foram indexados
   documentos nem executadas APIs LLM. Branch preservada, sem commit ou push.

Os comandos de operacao/manutencao estao no [guia do kit](kit-agentes.md).
Este aceite e reexecutavel localmente, mas nao e execucao da CI GitHub nem
comprovacao de compatibilidade em todas as versoes/plataformas suportadas.

## Revisao de integracao: correcoes P2

Em 20/09/2026, preservando o aceite local e sem commit, push ou refatoracao do
produto:

1. **SDK minimo de desenvolvimento.** A revisao confirmou que o teste de
    transporte importava `streamable_http_client`, ausente na fonte oficial do
    SDK 1.9.0, ainda permitido pelo intervalo de runtime. `requirements-dev.txt`
    agora fixa MCP 1.30.0; o extra dev em `pyproject.toml` exige 1.30.0 ate antes
    de 2.0.0. Runtime inalterado, sem afirmar compatibilidade revalidada de toda
    a faixa antiga. Duas regressoes em `tests/mcp/test_transport.py` conferem
    exclusao de 1.9/2.0, aceitacao de 1.30 e adequacao da versao instalada.
2. **Build documental estrito.** A revisao reproduziu YAML/template invalidos
    com exit 0 no Retype e aprovacao no verificador de links. `scripts/build_docs.cjs`
    passa a controlar `npm run docs:build`: rejeita diagnosticos WARNING/ERROR,
    contagens nao nulas, falhas de processo e resumo final ausente. Mensagens
    ANSI sao normalizadas apenas para classificacao; a saida original e mantida.
    Nao exige Retype Pro. O formato de diagnostico esta ligado ao Retype 4.6.0
    do lockfile e deve ser revisado em upgrades.

Evidencias desta rodada:

- `uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt --dry-run`:
   nenhuma mudanca necessaria no ambiente atual.
- O mesmo dry-run com `mcp==1.9.0` adicional foi rejeitado por conflito com
   MCP 1.30.0 (exit 1 esperado). Nenhum pacote foi instalado ou rebaixado.
- `pytest tests/mcp/test_transport.py -k dependencias_dev -q`: 2 passaram.
- Selecao Python consolidada do plano: **187 passaram em 22,73 s**, com os
   mesmos oito avisos de depreciacao da API antiga usada pelo cliente de produto.
- `npm --prefix docs run docs:test`: **13 passaram em 8,34 s**. Dez casos de
   classificacao de saida/processo; tres builds Retype reais em temporarios,
   aceitando a pagina valida e rejeitando YAML/template invalidos mesmo quando
   o Retype retorna zero. Testes em `tests/test_docs_build.cjs`.
- `npm --prefix docs run docs:build`: 15 paginas, zero erros e zero avisos
   pelo novo gate. O job documental da CI executa docs:test antes do build.

Os arquivos CJS ficam fora de docs/ e nao sao copiados ao site. A allowlist do
Graphify continua somente Python; nao foi ampliada para indexa-los. O lockfile
npm e as dependencias de runtime permanecem inalterados. A CI remota nao foi
executada. Integrar a entrega e preparar commits continuam passos separados.

## Metricas de sucesso

| Criterio | Meta proposta | Medicao atual |
|---|---|---|
| Rastreabilidade | Regras do recorte ligadas a especificacao, codigo e teste; lacunas cientificas explicitas. | Quatorze regras e quatro contratos arquiteturais mapeados; justificacao cientifica separada por acordo. |
| Preservacao | Invariantes e cenarios de referencia equivalentes, tolerancias definidas antes de migrar. | Fisica preservada; ServerState, traces e paridade com pipeline testados. |
| Cobertura | Medir ramos; considerar metas maiores em novo escopo por risco, sem impor percentual arbitrario. | 225/322 ramos (69,88%) no recorte de oito modulos; cobertura de estados RL e outra metrica. |
| Feedback | Selecao local ate 60 s, sem rede externa (HTTP local permitido). | Aceite: 185 sob cobertura em 22,97 s; revisao: 187 Python sem cobertura em 22,73 s e 13 Node em 8,34 s. |
| Documentacao | Build reproduzivel e links locais validos no uso local acordado. | Build estrito rejeita os casos invalidos; 13 regressoes Node; saida local sem avisos, sem deploy. |
| Arquitetura | Zero imports proibidos pelos contratos aprovados. | Quatro contratos satisfeitos; violacoes diretas/indiretas rejeitadas pelos testes; limites de analise documentados. |
| Manutencao | Contratos/testes orientam mudancas; avaliacao quantitativa antes/depois e trabalho futuro. | Startup injetavel, estado unico e dependencias verificadas; nao se alega reducao de tempo medida. |
| Reproducao | Revisao, ambiente, configuracao, seeds, dados autorizados e tolerancias ligados aos resultados. | Somente piloto sintetico; experimentos nao reexecutados. |

## Evolucoes fora do aceite

Os itens abaixo nao foram declarados concluidos; foram separados da entrega
local por confirmacao do mantenedor. Nao executar automaticamente.

1. Definir URL somente quando houver pedido de publicacao. Revisar fontes
   cientificas e conteudo historico no escopo academico. Manter separado o teste
   de UI/clientes externos da validacao SDK local entregue. Migrar API HTTP
   depreciada do cliente somente com compatibilidade de versoes definida.
   Nao presumir execucao remota de CI; revisar atomicidade e concorrencia a parte.
2. Separar os testes que treinam/carregam dados e definir metas de cobertura
   por risco; nao usar a suite completa ou apenas `-m 'not slow'` como gate rapido.
3. Complementar ADR-003 com limites de sessao e configuracao por execucao,
   preservando ADR-004 e os contratos de imports. Nao duplicar o motor no MCP.
4. Revisar limites entre consumo obrigatorio, teto e PCC, e a formula completa
   do reward. Qualquer correcao de modelo precisa de aprovacao e testes proprios.
5. Completar fontes das regras, contratos de acoes nos runs e metadados de
   reproducao. Os avisos atuais de fisica nao garantem equivalencia experimental.
6. Atualizar as demais paginas, incluindo protocolo/dados/resultados historicos;
   manter os gates de build e links aprovados ao mudar conteudo. Node portatil
   disponivel, mas PATH global e ambiente Python permanecem preservados.

## Criterio de conclusao de cada mudanca

Identificar regras afetadas; atualizar as duas visoes pertinentes; justificar
decisao relevante em ADR; executar testes afetados e gates; revisar diff e
impacto em runs; atualizar Graphify somente com codigo autorizado. Separar
fatos verificados, hipoteses e decisoes segundo o
workflow de conhecimento (`knowledge/workflow.md`).