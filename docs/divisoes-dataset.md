---
label: Divisoes do dataset
icon: calendar
order: 24
---

# Divisoes de treino, validacao e teste

Protocolo `divisoes_v1`, aprovado em 20/09/2026: cinco metodos selecionaveis
no dashboard/MCP, sem executar todos por padrao. Esta entrega nao escolhe o
protocolo cientifico definitivo nem executa experimentos sobre a base real.

## Escolha e execucao

1. Conecte o dashboard ao MCP e abra **Divisoes do dataset** no menu lateral.
2. Selecione explicitamente qualquer combinacao de um a cinco metodos.
3. Escolha **Dados ativos** ou **FEMS anual**. A segunda opcao usa a pasta,
   fazenda e ano informados, com o loader existente em `mes=0`, sem trocar a
   base nem a politica ativa do servidor. **Dados ativos** pode conter apenas
   janeiro; confirme o periodo na previa.
4. Ajuste proporcoes ou cortes mensais, episodios, intervalo de validacao e seeds. Clique
   **Planejar** para conferir dias, blocos e numero total de treinamentos.
5. **Treinar e validar selecionados** executa somente as divisoes do plano.
   Cada uma recebe agentes IQL novos; heuristico e sem-agente sao avaliados
   nos mesmos dias. Nao ha chamada ao LLM-juiz nem treino do par legado.
6. Depois de todos os treinos, a confirmacao **Liberar teste final deste plano**
   habilita **Avaliar teste final**. O teste nunca escolhe o checkpoint.

Sem metodos selecionados, nao e possivel planejar. Alterar a configuracao
invalida a previa para execucao ate gerar um novo plano. Repetir uma chamada
concluida no mesmo plano devolve o resultado existente, sem retreinar.

## Cinco metodos

| Identificador | Regra | Interpretacao |
| --- | --- | --- |
| `cronologico` | Primeiros dias para treino, seguintes para validacao, ultimos para teste | Operar em periodo futuro |
| `aleatorio` | Sorteio de dias completos; cada conjunto fica ordenado por data | Generalizacao dentro da mesma base; vizinhanca temporal pode favorecer resultados |
| `sazonal` | Blocos contiguos sorteados separadamente em cada ano/trimestre civil | Representacao dos trimestres presentes na base |
| `progressivo` | Treino crescente e validacoes sucessivas antes de um teste final fixo | Sensibilidade ao tamanho do historico e ao periodo de validacao |
| `mensal_fixo` | Cortes inclusivos por dia do calendario, repetidos em cada mes/ano | Blocos reservados em todos os meses presentes, sem sorteio |

Nos quatro metodos nao mensais, as proporcoes padrao sao 70% treino, 15%
validacao e o restante para teste. Elas nao afetam `mensal_fixo`.
Os tamanhos de treino e validacao usam arredondamento para baixo e minimo
de uma unidade. O teste recebe o restante. A unidade e o dia nos metodos
cronologico/aleatorio e o bloco por trimestre no sazonal. Conjuntos vazios
ou quantidade insuficiente de blocos geram erro, nunca fallback silencioso.

Com 365 dias, a divisao cronologica padrao tem **255/54/56 dias**; nao usa
fronteiras mensais. No sazonal, blocos de sete dias comecam no primeiro dia
disponivel do trimestre; a cauda pode ter menos dias. Lacunas tambem encerram
um bloco. Os trimestres civis nao equivalem a estacoes meteorologicas.

No progressivo com tres janelas, os treinos tem **147, 201 e 255 dias**,
cada validacao tem 54 dias e os ultimos 56 dias sao sempre teste. As janelas
anteriores deixam dias intermediarios sem uso. Validacao de uma janela pode
entrar no treino da seguinte, mas teste nunca entra. Cada janela recomeca o
aprendizado do zero, sem reaproveitar Q-tables.

### Blocos mensais fixos

Os parametros `dia_fim_treino` (padrao 24) e `dia_fim_validacao` (padrao 27)
sao dias inclusivos do calendario. Nao sao percentuais nem quantidades de
amostras e nao dependem da seed de divisao.

| Conjunto | Dias padrao em cada mes | Total em um 2025 completo |
| --- | --- | --- |
| Treino | 1 a 24 | 288 |
| Validacao | 25 a 27 | 36 |
| Teste | 28 ate o ultimo dia do mes | 41 |

Fevereiro de 2025 fornece um dia de teste, fevereiro bissexto fornece dois;
meses de 30 e 31 dias fornecem tres e quatro. Alterar os cortes para 20/25
em um 2025 completo produz 240/60/65 dias. O dia do primeiro corte pertence
somente ao treino, e a validacao comeca no dia seguinte.

Os cortes devem ser inteiros com `1 <= dia_fim_treino < dia_fim_validacao <= 30`.
Cada mes/ano presente precisa ter ao menos um dia disponivel em cada conjunto.
Por exemplo, um corte de validacao em 28 e rejeitado para fevereiro de 2025,
pois nao deixa teste. Meses parciais sao aceitos apenas se os tres conjuntos
ficarem nao vazios; lacunas nao sao preenchidas nem dias transferidos de outro
mes. A previa registra as datas realmente disponiveis, sem prometer cobertura
completa do calendario. Anos diferentes sao tratados separadamente.

No dashboard, os dois campos **Mensal: ultimo dia de treino/validacao** ficam
ativos quando esse metodo esta selecionado. Percentuais ficam desabilitados
quando apenas o mensal esta selecionado; em combinacoes, aplicam-se somente
aos outros metodos. Ambos os cortes constam no manifesto e nos metadados do run.

Cada conjunto mensal e percorrido em ordem cronologica. A mesma regra de SoC
dos demais experimentos vale: reinicio em 50% nas lacunas entre blocos, com
continuidade entre dias consecutivos. O metodo mede generalizacao em blocos
reservados dentro da base, nao previsao estritamente futura: treinos posteriores
no calendario podem anteceder a avaliacao de um bloco de teste de janeiro.
Os meses contribuem com quantidades diferentes de dias; a media global pondera
cada dia igualmente, nao cada mes. Dias adjacentes podem ser correlacionados.

## Seeds, custo e bateria

- Uma seed de treino, padrao 42, reiniciada a cada divisao; uma seed de divisao,
  tambem padrao 42, independente da primeira. O sorteio nao consome o RNG do
  motor. A ordem dos metodos nao altera seus sorteios ou seeds de treino.
- Mesmo numero de episodios por treinamento. Selecionar os cinco metodos
  com tres janelas progressivas exige sete treinos, nao cinco. O progressivo
  recebe mais computacao total. As avaliacoes acrescentam custo de execucao.
- SoC inicial de 50% em cada bloco independente. Dias consecutivos propagam
  o SoC; lacunas, mudancas de conjunto e retorno ao inicio do ciclo reiniciam
  em 50%. A mesma convencao vale para RL e baselines.
- Apenas treino atualiza as Q-tables. Validacao e teste usam acoes greedy,
  sem exploracao, atualizacoes ou insercao de estados novos nas Q-tables.
- O checkpoint e escolhido pelo menor custo medio diario de validacao no
  intervalo configurado. Intervalos maiores que o treino sao limitados ao
  numero de episodios. O resto do criterio de checkpoint e o do motor atual.

## Persistencia e MCP

| Ferramenta | Acao |
| --- | --- |
| `plan_dataset_splits` | Previa sem treino; `metodos` obrigatorio, parametros configuraveis |
| `get_split_experiment` | Consulta plano e resultados por `plano_id` |
| `train_split_experiment` | Treina/valida uma `divisao_id` do plano selecionado |
| `evaluate_split_test` | Avalia teste de uma divisao; exige `confirmar=true` e todos os treinos concluidos |

Cada run usa o formato existente de `outputs/runs/`, sem alterar `latest.txt`.
O historico e os metadados registram protocolo, datas/blocos, seeds, configuracao,
fonte e SHA-256 da representacao carregada (dias e curva de tarifa). Esse hash
identifica a entrada do motor, nao autentica a origem nem substitui o hash dos
arquivos brutos; sua reproducao pressupoe versoes compativeis do Pandas/NumPy.

O manifesto `outputs/divisoes/<plano_id>/plano.json` e atualizado apos cada
treino/teste. O dashboard tambem permite baixar o JSON. Planos e agentes ficam
em memoria ate reiniciar o servidor; reabertura automatica de planos persistidos
nao faz parte desta entrega. Nao reinicie o servidor entre treino e teste final.
Nao execute treinos concorrentes: o motor legado ainda usa o RNG global NumPy.

## Limites cientificos

Metodos diferentes podem reservar dias diferentes. Comparar apenas seus custos
absolutos nao identifica o melhor protocolo. Escolha pela pergunta cientifica
e pela validacao, nao pelo melhor resultado observado no teste. Datas reservadas
em um protocolo podem aparecer no treino de outro: executar todos nao cria um
holdout global independente para a escolha posterior entre protocolos.

O loader FEMS continua usando uma curva tarifaria de 24 horas e preenchimento
de lacunas com zero. O particionamento nao corrige esses limites nem comprova
qualidade/proveniencia dos valores. Um ano de uma fazenda nao comprova
generalizacao para outros anos ou fazendas. Runs legados nao ganham retroativamente
uma separacao treino/validacao/teste; o fluxo antigo permanece disponivel.

## Criterios de aceitacao

Testes sinteticos cobrem as 31 combinacoes nao vazias de metodos, disjuncao dos
conjuntos por janela, ordem temporal, preservacao dos blocos, seeds independentes,
SoC nas fronteiras, leitura nao mutante, persistencia, selecao no dashboard e
contratos MCP. O mensal tambem cobre fevereiro comum/bissexto, meses de 30/31
dias, cortes personalizados, conjuntos vazios e bases com varios anos.
Validacoes reais de desempenho e qualidade da base sao separadas.

Fontes no repositorio: `src/smarty_energy/data_splits.py`,
`src/smarty_energy/split_experiments.py`, `tests/test_data_splits.py`,
`tests/mcp/test_data_splits.py`, `tests/test_training.py`.