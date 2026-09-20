---
label: Regras de dominio
icon: checklist
order: 69
---

# Regras de dominio: energia, dados e politicas

Estado: comportamento atual caracterizado em 20/09/2026, base `8130f3f`.
Esta especificacao descreve o modelo implementado, nao certifica sua adequacao
a uma instalacao real. Nenhuma regra fisica foi alterada neste piloto.
O escopo foi ampliado para persistencia, selecao de dados e operacoes MCP.
Em 20/09/2026 a entrega de engenharia local foi encerrada por acordo, sem
deploy; a validacao cientifica/experimental permanece uma etapa separada.
Isso nao transforma regras observadas em regras cientificamente justificadas.

A [especificacao tecnica](arquitetura.md) explica os contratos e calculos.
O [plano de reorganizacao](reorganizacao.md) relaciona cada identificador abaixo
ao codigo e aos testes, e registra as decisoes e pendencias.

## Objetivo e limites

A bateria desloca energia entre horarios para auxiliar a gestao de custo da
fazenda. Seu uso deve respeitar a energia disponivel, as perdas e o limite
diario de movimentacao. Economia e qualidade de uma politica aprendida exigem
experimentos separados: nao sao demonstradas pelos testes de contrato.

Cada passo do modelo representa uma hora. Potencia (kW) e energia (kWh) sao
grandezas distintas, mesmo quando seus valores numericos coincidem nesse passo.
Os [parametros vigentes](configuracao.md) sao uma caracterizacao do codigo;
a origem empirica dos limites ainda precisa ser ligada a fontes revisadas.

## Catalogo de regras

| ID | Regra observada | Exemplo ou excecao |
|---|---|---|
| R-BAT-001 | Carga e descarga sofrem perdas; energia comprada ou gerada nao e igual a energia armazenada. | Com eficiencia de carga 0,92, 10 kWh AC armazenam 9,2 kWh DC quando os limites permitem. |
| R-BAT-002 | A carga para no limite superior; a descarga para no limite inferior. As duas compartilham um orcamento diario de energia movimentada no lado DC. | Esgotar esse orcamento impede novas operacoes, mesmo que ainda haja espaco ou energia na bateria. |
| R-BAT-003 | A virada do dia pode preservar a carga, mas renova o orcamento de movimentacao e os contadores operacionais. | Preservar o SoC nao significa preservar o throughput acumulado do dia anterior. |
| R-ACO-001 | O armazenamento pode carregar com excedente, manter, descarregar parcialmente ou solicitar carga pela rede. | A carga da rede depende de elegibilidade tarifaria; nao e uma ordem incondicional. |
| R-EST-001 | A politica tabular decide a partir de faixas discretas, nao de todas as grandezas continuas. | Mudar o significado de uma faixa pode invalidar politicas antigas mesmo sem mudar o tamanho da tabela. |
| R-SOC-001 | Por padrao, a avaliacao mensal e o treino transportam o SoC final para o proximo dia/episodio, na ordem fornecida. | Desligar a propagacao na avaliacao mensal reinicia cada dia no valor padrao; isso define outro protocolo experimental. |
| R-TRE-001 | O treino executa os episodios configurados e pode restaurar ao final a politica de menor custo avaliado em modo greedy. | Selecao de checkpoint nao e parada antecipada nem prova de convergencia; desligar selecao ou nao produzir checkpoint mantem a politica final. |
| R-RUN-001 | Runs com outra versao de estados ou chaves fora das faixas atuais sao rejeitados. | Diferencas fisicas registradas geram aviso, nao bloqueio. Um carregamento aceito nao comprova comparabilidade cientifica. |
| R-RUN-002 | Um run guarda as politicas, o historico fornecido e sua configuracao para reutilizacao entre pipeline e MCP. | O carregamento rejeita numero de acoes divergente quando registrado; nao e garantia de retomada identica de todo o treino. |
| R-DAD-001 | A fonte configurada e escolhida na ordem FEMS, Sheets, Excel. Uma falha nessa fonte nao deve trocar silenciosamente a base. | Um caminho Excel explicito so e usado quando FEMS e Sheets estao desativados. |
| R-MCP-001 | Trocar de dataset com sucesso reinicia o estado de analise em memoria; falha de leitura preserva o dataset ativo. | O teste nao garante recuperacao de falhas depois da leitura; arquivos de modelos salvos nao sao apagados pela troca. |
| R-MCP-002 | A operacao do servidor so comeca depois de preparar dados e estado. Pedir inicializacao novamente nao apaga uma analise em andamento. | Falha na preparacao impede iniciar o atendimento e permite nova tentativa; nao garante isolamento entre clientes. |
| R-MCP-003 | Uma analise ativa concentra dados, politicas e registros operacionais em um unico estado no processo. | Os traces da politica ativa e da congelada continuam separados; organizar o estado nao cria uma sessao independente por cliente. |
| R-MCP-004 | Um cliente pode consultar e comandar a analise pelo protocolo MCP, recebendo resultados ou erros explicitos. | Rejeicoes de indice/tipo testadas nao avancam a hora; novas sessoes de transporte do dashboard observam o mesmo estado do processo. |

## O que os agentes realmente controlam

- Armazenamento: seis comandos, detalhados na especificacao tecnica. Carga pela
  rede tenta primeiro aproveitar excedente de geracao, depois a rede elegivel.
- Consumo: a interface preserva oito codigos, mas os bits de bomba e secador
  sao ignorados pelas regras atuais. O bit do pivo participa da escolha do
  inicio de seu bloco obrigatorio, sujeito ao rescue da ultima janela.
- Gerente: escolhe entre tres tetos de consumo. A conciliacao entre teto,
  cargas obrigatorias e limite de conexao exige uma revisao propria; nao e
  certificada pelo piloto de bateria.

## Exemplos verificaveis

1. Sem limitacao ativa, fornecer 5 kWh AC a uma carga retira
   `5 / 0,95` kWh DC da bateria. O throughput contabiliza essa retirada DC.
2. Se um dia termina com SoC de 62,5%, a avaliacao com propagacao inicia o
   proximo nesse valor. Sem propagacao, usa o padrao configurado.
3. Solar exatamente igual a 15 kW pertence a faixa alta; estresse igual a 70
   pertence a faixa alta. As igualdades fazem parte do contrato.
4. Um run com fisica divergente pode emitir aviso e continuar. O pesquisador
   deve registrar a divergencia antes de comparar os resultados.
5. Tarifa igual ao limite de elegibilidade bloqueia a carga da rede, mas nao
   impede aproveitar excedente de geracao. Se o excedente esgota o orcamento
   diario de movimentacao, nao sobra throughput para a parcela da rede.

O encaminhamento mensal foi verificado nos quatro caminhos publicos, com
propagacao padrao, ligada e desligada. A integracao de dois dias foi exercitada
com decisores fixos nos caminhos RL e LLM, sem aprendizado nem consulta externa.
Isso verifica o protocolo de execucao, nao a qualidade desses decisores.

## Dados e politicas salvas

Os [contratos de dados](dados.md) distinguem a base escolhida dos arquivos
legados. Identificar fazenda, periodo e fonte e necessario antes de comparar
politicas; o rotulo da fonte nao e um hash nem prova de autenticidade.

O [MCP](mcp.md) permite reutilizar um run e seu SoC final, mas trocar a fazenda
reinicia politicas, snapshots, traces e metricas em memoria. Runs em disco
continuam disponiveis e precisam ser avaliados quanto a compatibilidade antes
de reutilizar. Arquivos pickle devem vir de fonte confiavel; nao sao formato
seguro para receber arquivos arbitrarios de terceiros.

Os testes desta etapa usam apenas dados sinteticos e arquivos temporarios.
Alem das funcoes diretas, dois testes exercitam stdio e HTTP locais com o SDK
e o cliente Python do dashboard. A resposta de um passo valido contem
observacao, reward e registro horario JSON; os erros de indice/tipo testados
nao avancam o ambiente. A interface visual, autenticacao e acessos remotos nao
foram validados. Nenhum processo de servidor permanece ativo apos esses testes.

Preparar a sessao e trocar a fazenda sao operacoes diferentes. A inicializacao
normal acontece uma vez antes do atendimento; uma solicitacao repetida nao e
um reset. Importar o modulo Python, por si so, nao le a base nem prepara uma
sessao operacional. Essa separacao facilita verificar o sistema sem acesso
aos dados de producao. As interfaces de linha de comando continuam iguais.
O estado ainda e compartilhado no processo, nao independente por cliente.
Esse estado agora e representado por um unico objeto, para reduzir o risco de
consultar componentes antigos depois de um reset ou troca de dados. Os testes
verificam sua identidade nessas operacoes e as cadeias separadas de SoC.
Nao se afirma que toda falha tenha rollback nem que operacoes simultaneas
sejam seguras. Essas garantias exigem decisoes e verificacoes separadas.

## Decisoes e lacunas

Para facilitar mudancas, o motor nao deve depender das telas nem do servidor
que o expoe; clientes MCP nao devem acessar diretamente a politica ou o estado
ativo. Quatro verificacoes de dependencias protegem essas direcoes, com
identificadores `A-DEP-001` a `A-DEP-004` na [visao tecnica](arquitetura.md).
Sao criterios de organizacao do software, nao novas restricoes fisicas nem
prova de isolamento ou seguranca. Falhar nesses criterios bloqueia o gate de
arquitetura; alteracoes na organizacao exigem atualizar a decisao e os testes.

A decisao de preservar o comportamento durante a reorganizacao esta em
`ADR-001` no plano; `ADR-002` registra a inicializacao explicita do MCP e
`ADR-003` a representacao do estado unico. `ADR-004` registra os limites de imports.
Os valores de capacidade, eficiencia, throughput, horarios
e metas foram conferidos no codigo, mas essa verificacao nao substitui fonte
tecnica, bibliografica ou evidencia experimental para justifica-los.

Continuam pendentes a fundamentacao dos parametros, a revisao completa do
reward, a validacao completa de dados/MCP e a validade externa do simulador. Nao
preencher essas lacunas com justificativas inferidas dos comentarios do codigo.