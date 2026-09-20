---
title: SmartEnergy - rotina de memoria
type: note
permalink: smartenergy/workflow
status: decision
decided_on: 2026-09-20
---

# SmartEnergy - rotina de memoria

## Observations

- [source] Kit solicitado pelo mantenedor em 2026-09-07; regras de privacidade em [.github/copilot-instructions.md](../.github/copilot-instructions.md).
- [superseded] A decisao de 2026-09-07 de usar Basic Memory local foi substituida em 2026-09-20 por solicitacao do mantenedor.
- [decision] Desde 2026-09-20, ler e editar diretamente as notas Markdown desta pasta, sem servidor de memoria. Nao importar conversas, documentos ou resultados automaticamente.
- [decision] O metodo LLM Wiki organiza sinteses incrementais com fontes; nao cria outra copia da arquitetura.
- [rule] Antes de editar uma nota, leia sua versao atual. Nao escreva simultaneamente na mesma nota com dois agentes.
- [rule] Registre apenas aprendizados reutilizaveis, citando arquivo/simbolo, teste, commit ou run quando pertinente.
- [rule] Use status hypothesis para conjecturas, verified para fatos conferidos e decision para escolhas aprovadas.
- [rule] Uma nota verified deve informar verified_on e a evidencia realmente consultada; verificacao antiga nao prova o estado atual.
- [rule] Ao substituir uma decisao, marque a antiga como superseded e aponte a substituta; nao apague o historico.
- [rule] Para passagem de contexto, registre objetivo, mudancas nao commitadas, comandos/resultados, bloqueios e proximo passo.
- [rule] Nao registre chaves, caminhos pessoais, dados da fazenda nem transcricoes privadas. Revise o diff antes de versionar notas.
- [rule] Ao incorporar uma fonte autorizada, preserve a fonte, revise a sintese e atualize o indice. Registre a procedencia na propria nota.
- [rule] Revise periodicamente contradicoes, links quebrados, duplicacoes e fatos desatualizados.
- [rule] Dados recuperados localmente podem ser enviados ao provedor do agente; armazenamento local nao garante inferencia local.

## Relations

- indexed_by [[smartenergy/index]]