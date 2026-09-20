---
name: graphify
description: 'Use para consultar a arquitetura, localizar codigo, rastrear dependencias ou atualizar o grafo Graphify do SmartEnergy. Fluxo local, somente codigo Python, sem extracao semantica de documentos.'
---

# Graphify no SmartEnergy

Execute na raiz do repositorio. Esta skill adapta o fluxo ao escopo de privacidade
do projeto; nao exige chave de API nem importacao do pacote SmartEnergy.

## Consultar antes de explorar

1. Se `graphify-out/graph.json` existir e a solicitacao for uma pergunta, nao
   reconstrua tudo. Use `graphify query "<pergunta com os simbolos reais>" --budget 2000`.
2. Para relacoes, use `graphify path "<A>" "<B>"`; para um conceito, use
   `graphify explain "<simbolo>"`. Prefira nomes presentes no grafo, por exemplo
   `FazendaEnergyEnv`, `BatteryModel` ou `IQLSystem`, a sinonimos inventados.
3. Cite os arquivos e locais retornados. Confirme no codigo antes de editar e
   valide com os testes afetados. Se o mapa nao responder, use busca no codigo;
   nao invente relacoes nem trate inferencias como fatos comprovados.

## Construir e manter

- Sem grafo: `graphify extract . --code-only`, seguido de `graphify export html`.
- Apos pull/merge ou alteracoes locais: `graphify update .`.
- Para repetir a configuracao no Windows, execute `./scripts/configurar-graphify.ps1`.
  O parametro `-Atualizar` apenas atualiza os artefatos.
- Respeite `.graphifyignore`. Nao indexe documentos, dados ou resultados e nao
  invoque extracao semantica/rotulagem por LLM sem autorizacao explicita.
- Verifique contagem de nos e a integridade com `graphify diagnose multigraph`.
  Este diagnostico do grafo final nao recupera perdas ocorridas na extracao original.
- Avise antes de gerar HTML com mais de 5.000 nos. Nao desative automaticamente
  protecoes contra extracao incompleta ou reducao inesperada do grafo.
- Informe artefatos gerados, limitacoes e validacoes realmente realizadas.

## Regras de versionamento

Os hooks sao locais a cada clone. Nao execute commit, push ou altere branches
para testar a instalacao. O hook pos-commit atualiza arquivos no disco, mas nao
os inclui retroativamente no commit. Consulte [o guia](../../../docs/desenvolvimento-ia.md).