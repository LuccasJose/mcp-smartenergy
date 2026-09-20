## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, your first action should be `graphify query "<question>"` when `graphify-out/graph.json`
exists. Use `graphify path "<A>" "<B>"` for relationship questions and `graphify explain "<concept>"`
for focused-concept questions. These return a scoped subgraph, usually much smaller than the full
report or raw grep output.

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>",
"explain the architecture", or anything that depends on how files or classes relate.

If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read `graphify-out/GRAPH_REPORT.md`
only for broad architecture review or when query/path/explain do not surface enough context. Only read
source files when (a) modifying/debugging specific code, (b) the graph lacks the needed detail, or
(c) the graph is missing or stale.

Type `/graphify` in Copilot Chat to build or update the graph.

## SmartEnergy: contexto e limites

- Consulte [CONTEXT.md](../CONTEXT.md) e, conforme a tarefa,
	[arquitetura](../docs/arquitetura.md) e [componentes](../docs/componentes.md).
	Confirme valores e comportamento no codigo atual; documentos e grafo podem ficar desatualizados.
- A camada MCP deve reutilizar o motor em `src/smarty_energy`; nao duplique
	ambiente, modelo de bateria, configuracao ou carregamento de dados.
- Preserve restricoes fisicas, unidades kW/kWh, propagacao de SoC, codificacao
	de estados/acoes e compatibilidade dos runs. Mudancas nesses contratos exigem
	testes e documentacao dos impactos.
- Antes de editar, confirme os trechos apontados pelo grafo. Relacoes `INFERRED`
	nao sao provas de execucao; ausencia de uma aresta nao prova independencia.
- Use o interpretador selecionado do projeto para testes, nao o ambiente isolado
	do Graphify. Execute os testes afetados; nao inicie treino longo, downloads de
	datasets, LLM-juiz ou chamadas pagas para validar uma alteracao sem necessidade.
- Nao apresente testes nao executados ou numeros experimentais como resultados verificados.

## Graphify: politica local do projeto

- O escopo autorizado esta em [.graphifyignore](../.graphifyignore): somente
	codigo Python do produto, scripts e testes. Nao amplie o escopo automaticamente.
- Para construir sem grafo: `graphify extract . --code-only`. Para atualizar:
	`graphify update .`. Nao use extracao semantica, `graphify label` ou APIs
	externas sem solicitacao explicita. A skill local do projeto documenta este fluxo.
- Depois de pull/merge ou de alteracoes locais relevantes, atualize antes de consultar.
	Se a protecao contra reducao do grafo disparar, investigue antes de usar `--force`.
- Nunca indexe nem publique segredos, dados da fazenda, documentos privados,
	resultados de treino, caminhos de maquina ou historico privado de consultas.
- O grafo e um indice auxiliar, nao substitui testes, revisao de codigo ou registro
	das decisoes. Veja [o guia de uso e reproducao](../docs/desenvolvimento-ia.md).
