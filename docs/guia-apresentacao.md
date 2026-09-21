---
label: Guia de apresentacao
icon: book
order: 67
---

# Guia de apresentacao das mudancas

Roteiro para equipe ou orientador, com duracao sugerida de 10 a 15 minutos.
Referencia: entrega ate o commit `0e51402`, na branch
`refactor/reorganizacao-contratos`. Preparado em 21/09/2026.

## Mensagem principal

> O objetivo desta etapa foi tornar o projeto mais explicavel, testavel e
> preparado para experimentos reproduziveis. Organizei o estado do servidor,
> protegi contratos com testes e implementei cinco formas selecionaveis de
> separar treinamento, validacao e teste. Ainda nao estou apresentando uma
> melhoria comprovada de economia energetica.

## Roteiro de fala

### 1. Motivacao e escopo (1 minuto)

**Fala sugerida:**

> Parti de tres necessidades: documentacao coerente com o codigo, decisoes
> tecnicas justificaveis no trabalho academico e menor risco ao fazer mudancas.
> Por isso, comecei protegendo o comportamento existente antes de acrescentar
> novos protocolos experimentais.

Mostre o [plano de reorganizacao](reorganizacao.md) e as
[regras de dominio](regras-dominio.md). Explique que o motor energetico ja
existia: esta entrega nao criou o algoritmo IQL nem reescreveu a fisica.

### 2. Organizacao do servidor e protecao do motor (3 minutos)

| Antes | Mudanca | Motivo |
| --- | --- | --- |
| Importar o servidor carregava o dataset e construia objetos operacionais | `initialize()` prepara explicitamente o servidor | Separar importacao de execucao e permitir testes com dados sinteticos |
| Estado operacional espalhado em variaveis globais | `ServerState` reune dados, agentes, ambiente, tracker e snapshots | Tornar visiveis os objetos que uma analise usa e modifica |
| Dependencias entre camadas sem verificacao automatica desses contratos | Quatro contratos de imports | Detectar acoplamentos indevidos entre motor, MCP e clientes |
| Mudancas podiam afetar contratos sem uma verificacao focada | Testes de bateria, estados/acoes, SoC, persistencia e transporte | Detectar regressoes nos comportamentos protegidos |

**Fala sugerida ao abrir `ServerState`:**

> Esta classe nao e um novo modelo de bateria nem um banco de dados. Ela agrupa
> as referencias do estado operacional do servidor. O motor continua sendo o
> mesmo, mas agora os acessos passam por um objeto explicito.

Mostre `src/smarty_energy/mcp/state.py`, depois `initialize` e `get_state` em
`src/smarty_energy/mcp/server.py`. Destaque que a inicializacao prepara os
objetos antes de publicar o estado. O servidor ainda compartilha estado entre
clientes; encapsulamento nao significa isolamento concorrente ou multiusuario.

Em `pyproject.toml`, mostre um contrato de imports, nao todos os detalhes.
Mencione tambem a correcao de serializacao JSON de booleanos NumPy no MCP.
Nao apresente a protecao estatica como prova de todas as dependencias em runtime.

### 3. Dados disponiveis e problema experimental (1 minuto)

**Fala sugerida:**

> A verificacao temporal dos Parquet identificou 2025 completo para a FAZ-002:
> 365 dias e 8.760 horas. Cada uma das sete series de consumo e das duas series
> de geracao, alem da fatura, tinha todos os horarios esperados, sem duplicatas
> por serie. Mas o carregamento padrao selecionava janeiro.

Acrescente duas ressalvas:

- A verificacao executada em 20/09/2026 cobriu datas e identificadores, nao a
  qualidade dos valores energeticos nem sua origem como medicoes reais.
- No fluxo legado, os dias de selecao tambem podem participar do treino.
  Uma avaliacao sobre os mesmos dados nao comprova generalizacao.

Nao abra linhas de dados privados durante a apresentacao. O novo protocolo
trabalha com a base selecionada e nao corrige automaticamente problemas do loader.

### 4. Cinco protocolos selecionaveis (3 minutos)

| Metodo | Regra | Pergunta que ajuda a investigar |
| --- | --- | --- |
| Cronologico | Treino primeiro, validacao depois, teste no fim | A politica funciona em periodos posteriores? |
| Aleatorio por dias | Sorteio de dias completos | Funciona em outros dias da mesma base? |
| Blocos por trimestre | Sorteio de blocos dentro de cada trimestre civil | Funciona nas diferentes condicoes presentes ao longo do ano? |
| Progressivo | Treinos do zero com historico crescente e validacoes sucessivas | Quanto o resultado depende do historico e da janela de validacao? |
| Mensal fixo | Mesmos cortes de calendario em cada mes | Funciona nos blocos reservados de cada mes? |

**Exemplo principal:** no mensal fixo, treino de 1 a 24, validacao de 25 a 27
e teste de 28 ate o fim do mes. Em 2025 completo, sao **288/36/41 dias**.
O dia 24 pertence apenas ao treino. Os cortes sao configuraveis; fevereiro
comum contribui com somente um dia de teste no padrao.

**Fala sugerida:**

> Nao escolhi automaticamente um metodo vencedor. Cada divisao responde a uma
> pergunta diferente. A selecao e explicita e pode combinar de um a cinco
> metodos. Os conjuntos sao separados dentro de cada divisao, mas os testes
> de metodos diferentes nao formam um holdout global independente.

Mostre `construir_divisoes` em `src/smarty_energy/data_splits.py`: a funcao
organiza indices dos dias, sem treinar nem modificar os valores da base.
No mensal, destaque os limites inclusivos e a rejeicao de conjuntos vazios
em cada mes/ano. Nao ha sorteio nem aplicacao de percentuais nesse metodo.

### 5. Execucao, seeds e SoC (2 minutos)

Mostre `PlanoDivisoes` em `src/smarty_energy/split_experiments.py`.

**Fala sugerida:**

> Separei planejamento, treinamento com validacao e teste final. Cada divisao
> cria agentes novos e reutiliza o motor. O checkpoint e escolhido pela
> validacao; o teste exige confirmacao depois de todos os treinos do plano.
> Esses experimentos nao substituem a politica ativa nem o run padrao.

- A seed de treino controla a exploracao dos agentes. A seed de divisao
  controla os sorteios dos metodos aleatorio e sazonal. Ambas ficam registradas.
- Dias consecutivos propagam SoC. Cada bloco descontinuo e o retorno ao inicio
  do ciclo recomecam em 50%, igualmente para RL e baselines.
- Os fluxos antigos preservam sua propagacao padrao. O novo protocolo passa
  explicitamente os indices de reinicio, sem alterar a fisica da bateria.
- Os runs registram cortes, periodos, seeds, configuracao e hash da entrada
  carregada. Esse hash identifica a entrada, nao autentica a origem dos dados.
- Cinco metodos com tres janelas progressivas representam sete treinamentos.
  Mesmo numero de episodios por treino nao significa mesmo custo total por metodo.

### 6. Demonstracao do dashboard (2 minutos)

Use preferencialmente uma base sintetica com 365 dias e identifique-a como tal.
Uma previa sintetica mostra funcionamento, nao desempenho da fazenda real.

1. Conecte ao MCP e abra **Divisoes do dataset**. Mostre a fonte e o periodo.
2. Selecione apenas **Blocos mensais fixos**; mantenha os cortes 24/27.
3. Clique **Planejar**. Explique que isso nao executa treino.
4. Mostre 288/36/41 dias, um treinamento e os periodos por conjunto.
5. Mude os cortes para 20/25: a previa anterior fica desatualizada. Planeje
   novamente e mostre 240/60/65 dias, para um ano de 365 dias completo.
6. Selecione os cinco metodos com tres janelas e mostre sete treinamentos.
7. Mostre o teste final bloqueado antes do treino e as descricoes dos campos.

Nao clique em **Treinar e validar selecionados**, **Avaliar teste final**,
**Executar o juiz** ou **Ativar fazenda** apenas para ilustrar o fluxo.
Caso queira mostrar resultados, prepare um experimento autorizado antes,
com fonte, configuracao e natureza sintetica/real claramente identificadas.

### 7. Verificacao e fechamento (1 minuto)

**Fala sugerida:**

> Na ultima regressao local desta entrega, 275 testes passaram. Eles cobrem
> contratos do motor, persistencia, transporte MCP, divisao dos dados e
> interacoes do painel com dados sinteticos. Isso verifica o software, nao
> prova que a politica economiza energia ou generaliza para outra fazenda.

Resultado registrado em 20/09/2026, nao reexecutado para produzir este guia:
275 testes aprovados na selecao explicita, com oito avisos conhecidos de
depreciacao do cliente HTTP. Ruff e hooks passaram; documentacao e links
locais foram validados. Nao foi a suite inteira nem validacao de CI remota.

> A entrega prepara a infraestrutura experimental e torna as decisoes mais
> rastreaveis. Os proximos passos sao auditar os valores da base, definir o
> protocolo cientifico e executar os experimentos com orcamento e criterios
> registrados antes de observar os resultados de teste.

## Ordem curta para mostrar o codigo

As referencias abaixo sao caminhos relativos ao repositorio, nao arquivos
copiados para este site. Abra somente os trechos indicados durante a fala.

| Ordem | Arquivo e simbolo | O que destacar |
| --- | --- | --- |
| 1 | `src/smarty_energy/mcp/state.py` / `ServerState` | Estado operacional explicito |
| 2 | `src/smarty_energy/mcp/server.py` / `initialize` | Carregamento deixa de ocorrer na importacao |
| 3 | `src/smarty_energy/data_splits.py` / `construir_divisoes` | Cinco regras, sem treinamento ou duplicacao dos dados |
| 4 | `src/smarty_energy/split_experiments.py` / `treinar_divisao`, `avaliar_teste` | Validacao separada, teste explicito e persistencia |
| 5 | `tests/test_data_splits.py` / `test_mensal_fixo_padrao_e_blocos_soc` | Evidencia executavel dos cortes e blocos |
| 6 | `src/smarty_energy/mcp/dashboard/pages/8_Divisoes_Dataset.py` | Cliente que solicita as operacoes via MCP |

Se houver tempo, mostre os argumentos de reinicio de SoC em
`src/smarty_energy/training.py` e `src/smarty_energy/agents.py`, e o parametro
`definir_como_latest` em `src/smarty_energy/runs.py`. Os defaults preservam
o fluxo legado; o experimento isolado opta pelo comportamento novo.

## Perguntas provaveis

**Qual metodo e o melhor?** Depende da pergunta cientifica. Cronologico testa
periodos posteriores; mensal e sazonal reservam condicoes dentro do mesmo ano.
Custos em periodos diferentes nao permitem escolher um vencedor diretamente.

**Por que nao embaralhar horas?** Dias completos preservam as trajetorias
diarias e as restricoes operacionais. Horas isoladas quebrariam essas sequencias.

**Por que reiniciar o SoC?** Para nao transportar energia artificialmente entre
dias que nao sao consecutivos no calendario. E uma convencao experimental
explicita, nao uma afirmacao sobre a bateria real entre esses periodos.

**Os agentes ja melhoraram?** Esta entrega nao mediu melhoria real de desempenho.
Testes sinteticos e demos de interface nao sao resultados cientificos.

**Toda a avaliacao agora usa holdout?** Nao. O novo fluxo de divisoes separa
os conjuntos; o treino e a avaliacao legados continuam disponiveis.

**O servidor suporta varios usuarios isolados?** Nao. `ServerState` centraliza
o estado, mas nao implementa isolamento concorrente nem elimina o RNG global.

**Posso fechar o servidor e retomar o plano?** Os runs e manifestos sao salvos,
mas a retomada automatica do plano ativo ainda nao esta implementada.

**O que foi publicado?** Sete commits foram enviados para
`refactor/reorganizacao-contratos`, ate `0e51402`. Nao houve merge na `main`
nem deploy da documentacao nesta entrega. O grafo e um indice auxiliar local,
nao substitui testes, codigo ou evidencias experimentais.

## Materiais de apoio

- [Reorganizacao e decisoes](reorganizacao.md).
- [Protocolos de divisao](divisoes-dataset.md).
- [Arquitetura](arquitetura.md) e [regras de dominio](regras-dominio.md).
- [Execucao e descricoes do dashboard](execucao-mcp.md).
- [Catalogo MCP](mcp.md) e [kit de verificacao](kit-agentes.md).

## Nota de preparacao

As falas sao sugestoes para explicar a entrega, nao alegacoes de resultados
novos. O historico Git, `ServerState` e o protocolo atual foram conferidos
para este roteiro. As contagens de testes e da base temporal referem-se as
verificacoes anteriores registradas nesta entrega. Antes da apresentacao,
confirme a branch, a fonte da demonstracao e a disponibilidade dos servidores;
nao apresente a previa sintetica como dataset real ou como experimento concluido.