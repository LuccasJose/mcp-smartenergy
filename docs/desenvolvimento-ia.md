# Graphify — guia de configuração para qualquer agente

Para notas locais em Markdown, Context7 e verificacoes automaticas,
consulte o [kit de desenvolvimento com agentes](kit-agentes.md).

Este guia pode ser seguido por uma pessoa ou por um agente com acesso ao terminal
e aos arquivos do repositório, em **Windows, macOS ou Linux**, independentemente
do editor. Não depende de tarefas do VS Code, de scripts próprios ou de um servidor MCP.

**Fonte:** [documentação oficial do Graphify](https://github.com/Graphify-Labs/graphify),
consultada em **07/09/2026**, quando a versão publicada era **0.9.55**.
Os comandos abaixo são reproduzidos da documentação oficial; as explicações foram
adaptadas para português. As restrições específicas do SmartEnergy estão identificadas
separadamente — este documento não é uma cópia integral nem documentação oficial.

## Pedido pronto para enviar ao seu agente

Abra o clone local do projeto e envie o texto abaixo, anexando este guia ou indicando
sua localização. O agente precisa ter permissão para executar comandos; em um chat
sem acesso à máquina, ele poderá apenas orientar a execução manual.

> Leia e execute o guia docs/desenvolvimento-ia.md deste repositório para configurar
> o Graphify na minha máquina e neste clone. Identifique o sistema operacional,
> o shell, as ferramentas já instaladas e o assistente que estou usando. Se não
> conseguir identificar o assistente, pergunte qual é antes de escolher a integração.
>
> Siga os passos numerados do guia, consultando as fontes oficiais. Reaproveite
> instalações válidas; prefira uv ou pipx para manter o Graphify isolado das
> dependências da aplicação. Informe a versão utilizada e não faça downgrade ou
> atualização de uma instalação existente sem necessidade e confirmação.
>
> Preserve as instruções, skills, hooks e alterações locais existentes. Respeite
> o escopo de privacidade do projeto: somente código, sem extração semântica,
> sem pedir chaves de API e sem enviar documentos ou dados da fazenda a modelos externos.
> Use o CLI com --code-only para a primeira extração ou update se já houver grafo.
>
> Configure apenas a integração do meu assistente e os hooks deste clone. Não crie
> tarefas de editor, CI, servidores ou scripts novos. Não altere o código da aplicação,
> não inicie treinos, não faça commit/push e não troque de branch para testar hooks.
> Se houver bloqueio de permissão ou senha administrativa, explique o passo manual
> necessário e pare; não contorne proteções nem solicite segredos pelo chat.
>
> Ao terminar, valide versão, artefatos, consulta ao grafo e status dos hooks.
> Informe o que foi executado, quais arquivos mudaram, os avisos encontrados e
> qualquer etapa que não pôde concluir. Não afirme que algo funciona sem verificar.

## 1. Conferir o ambiente

Execute os passos na **raiz do clone local**. O ponto `.` dos comandos significa
essa pasta, não a pasta de documentação.

Conforme os [pré-requisitos oficiais](https://github.com/Graphify-Labs/graphify#prerequisites),
são necessários Python **3.10+** e **uv** (recomendado) ou **pipx**. Para os hooks,
o Git deve estar instalado e a pasta deve ser um repositório Git.

- Identifique o sistema, o shell e o assistente; não presuma que todos usam VS Code.
- Confira se o Graphify já funciona com `graphify --version`.
- Inspecione o estado do Git e as configurações existentes antes de modificá-las.
- Se faltarem pré-requisitos, siga a [instalação oficial do uv](https://docs.astral.sh/uv/getting-started/installation/)
  ou do [pipx](https://pipx.pypa.io/stable/installation/), adequada ao sistema.
  Não copie comandos administrativos de outro sistema operacional.

## 2. Instalar a ferramenta em ambiente isolado

Fonte: [Install](https://github.com/Graphify-Labs/graphify#install).
Escolha **uma** alternativa; não instale com os dois gerenciadores.

Recomendação oficial:

```text
uv tool install graphifyy
```

Alternativa oficial:

```text
pipx install graphifyy
```

O pacote oficial é **graphifyy**, com dois `y`; o comando é **graphify**.
Não adicione essa ferramenta às dependências de execução do SmartEnergy.

**Convenção deste projeto:** a versão já validada é **0.9.55**. Para reproduzi-la
em uma instalação nova, use `uv tool install graphifyy==0.9.55` ou
`pipx install graphifyy==0.9.55`, em vez do comando sem versão.
Essa fixação é do projeto, não uma exigência da documentação oficial.

Confirme:

```text
graphify --version
```

Se o terminal não encontrar o comando, use `uv tool update-shell` ou
`pipx ensurepath`, conforme a instalação, e abra um novo terminal. O agente pode
localizar o diretório de executáveis do uv com `uv tool dir --bin`; não deve
presumir um caminho pessoal de outro integrante da equipe.

## 3. Criar ou atualizar o mapa local

Fontes: [Privacy](https://github.com/Graphify-Labs/graphify#privacy) e
[Full command reference](https://github.com/Graphify-Labs/graphify#full-command-reference).

**Política específica deste repositório:** preserve o escopo de
`.graphifyignore` e as exclusões de `.gitignore`.
Somente código Python do produto, scripts, testes e pontos de entrada entram no mapa.
Documentos, dados da fazenda, notebooks, resultados, ambientes e segredos ficam fora.
Não use opções que desativem essas exclusões.

Se ainda **não existir** `graphify-out/graph.json`:

```text
graphify extract . --code-only
```

Se o grafo **já existir**:

```text
graphify update .
```

Confira que a operação terminou sem falhas e que o grafo não ficou vazio.
Se houver aviso de extração incompleta ou redução inesperada, investigue;
não aplique `--force` automaticamente.

Para gerar ou atualizar a visualização:

```text
graphify export html
```

Avise antes de visualizar grafos com mais de 5.000 nós. A extração de código
usa AST local e não requer chave de API. Instalar dependências pode exigir internet;
isso é diferente de enviar o código para análise por LLM.

### Comando no chat não é comando de terminal

O início rápido oficial também mostra `graphify install` para registrar a skill
e `/graphify .` **dentro do chat do assistente**, quando há suporte a skills.
A etapa seguinte apresenta as integrações explícitas por plataforma.

No terminal, use os comandos **sem a barra inicial**, como `graphify update .`.
Em especial, não cole `/graphify .` no PowerShell. O parâmetro `--code-only`
pertence ao comando `graphify extract`, não ao comando de chat.
Para preservar a política local, este guia usa o fluxo CLI acima em vez de
depender do comportamento padrão de uma skill de outra plataforma.

## 4. Integrar ao assistente utilizado

Fonte: [Make your assistant always use the graph](https://github.com/Graphify-Labs/graphify#make-your-assistant-always-use-the-graph).
Na raiz do projeto, execute **somente a linha correspondente ao seu assistente**:

| Assistente | Comando oficial |
| --- | --- |
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| Cursor | `graphify cursor install` |
| Gemini CLI | `graphify gemini install` |
| GitHub Copilot no VS Code | `graphify vscode install` |
| GitHub Copilot CLI | `graphify copilot install` |
| OpenCode | `graphify opencode install` |
| Aider | `graphify aider install` |
| Framework compatível com Agent Skills | `graphify agents install` |

Para outros assistentes, consulte a lista completa na fonte oficial; não invente
nomes de plataforma. Se não houver integração nativa, um agente com terminal ainda
pode consultar o CLI por solicitação explícita, sem suporte a `/graphify`.

Os arquivos criados e o mecanismo de integração variam: algumas plataformas usam
instruções persistentes; outras também oferecem hooks do próprio assistente.
Não confunda esses hooks com os hooks do Git da etapa 5. Em particular, Copilot
CLI e Copilot no VS Code possuem comandos de instalação diferentes.

A documentação também permite instalar a skill no projeto, em vez do perfil do
usuário, nas plataformas compatíveis. Exemplo oficial para Codex:

```text
graphify install --project --platform codex
```

Isso é uma alternativa de escopo para a skill, não uma instalação do executável
para os colegas nem substituto dos hooks do Git. Não acrescente `--project`
indiscriminadamente a todos os comandos: confira o suporte da plataforma.

**Neste repositório:** preserve as instruções existentes do Copilot (`.github/copilot-instructions.md`)
e a skill local (`.github/skills/graphify/SKILL.md`). Não sobrescreva personalizações
sem comparar o conteúdo. As instruções orientam o agente a consultar o mapa, mas
não garantem que ele o usará em toda resposta; confirme com uma consulta real.

## 5. Ativar a atualização pelo Git neste clone

Fonte: [Team setup — Recommended workflow](https://github.com/Graphify-Labs/graphify#recommended-workflow).

```text
graphify hook install
graphify hook status
```

O instalador configura os hooks `post-commit` e `post-checkout` e um merge driver
para o JSON do grafo. Preserve hooks preexistentes e confira as mudanças.

| Ação normal de trabalho | Comportamento após instalar os hooks |
| --- | --- |
| Commit | Reconstrução local de código em segundo plano |
| Troca de branch | Reconstrução local; checkout de arquivo isolado não equivale a trocar branch |
| Pull ou merge | Execute `graphify update .` em seguida |
| Consulta após editar sem commit | Execute `graphify update .` antes, se o mapa estiver desatualizado |
| Push | Não instala a ferramenta nem os hooks na máquina dos colegas |

Pode haver um pequeno atraso entre o commit e a conclusão da reconstrução.
Cada clone precisa de seus próprios hooks. Após reinstalar/atualizar a ferramenta
ou trocar seu interpretador, execute `graphify hook install` novamente.
Não faça commits fictícios nem troque de branch somente para testar a instalação.

## 6. Validar e começar a usar

Execute os comandos abaixo no terminal; os símbolos são exemplos reais deste projeto:

```text
graphify --version
graphify hook status
graphify query "FazendaEnergyEnv BatteryModel" --budget 2000
graphify explain "IQLSystem"
graphify path "FazendaEnergyEnv" "BatteryModel"
```

O agente deve verificar e informar:

- A versão detectada e qual integração foi instalada.
- O status dos hooks e do merge driver.
- A existência de um grafo não vazio, de um relatório e do HTML.
- O resultado de uma consulta, com símbolos e referências de origem.
- Os arquivos modificados e qualquer aviso ou etapa pendente.

Depois, peça ao seu agente, por exemplo:

> Consulte o Graphify para explicar como FazendaEnergyEnv se relaciona com
> BatteryModel. Cite os arquivos e confirme no código os trechos relevantes.

Use nomes reais de símbolos nas consultas CLI, pois ele não traduz automaticamente
sinônimos ou perguntas entre idiomas. Relações `INFERRED` são inferências, não
provas de execução. Se o grafo não responder, consulte o código e os testes.
O contexto do domínio (`CONTEXT.md`) e a [arquitetura](arquitetura.md) complementam o mapa.

## O que é compartilhado e o que fica local

Fonte: [Team setup](https://github.com/Graphify-Labs/graphify#team-setup).

| Item | Como chega aos colegas |
| --- | --- |
| Este guia, instruções e regras de exclusão | Pelo Git, depois de commit e push explícitos |
| `graphify-out/graph.json` | Mapa compartilhável e consultável |
| `graphify-out/GRAPH_REPORT.md` | Relatório compartilhável |
| `graphify-out/graph.html` | Visualização compartilhável; não exige instalar Graphify para abrir |
| `graphify-out/manifest.json` | Manifesto com caminhos relativos, compartilhável |
| Executável, interpretador e hooks do Git | Instalação local por pessoa/clone |
| Cache, custos, logs e memória de consultas | Permanecem locais conforme `.gitignore` |

**Reconstruir não é versionar.** O hook pós-commit não inclui retroativamente os
artefatos no commit nem faz push. Para compartilhar o mapa junto com o código,
atualize antes de preparar o commit, revise os artefatos e inclua-os explicitamente.
Este guia não configura commits automáticos, CI ou servidores compartilhados.

Revise os artefatos antes de publicar: eles contêm nomes, caminhos e trechos de
comentários/docstrings. A extração local **não torna o seu assistente offline**:
conteúdo consultado no chat pode ser enviado ao provedor do modelo conforme sua
configuração. O HTML pode carregar bibliotecas de visualização de CDN.

## Problemas comuns

Fonte: [Troubleshooting](https://github.com/Graphify-Labs/graphify#troubleshooting).

| Situação | Como proceder |
| --- | --- |
| Comando não encontrado após instalar | Corrigir o PATH com o gerenciador usado e abrir novo terminal; veja etapa 2 |
| Importação de Graphify falha no Python da aplicação | Usar o CLI da instalação isolada; não instalar outra cópia na aplicação como atalho |
| Skill ausente no assistente | Conferir a plataforma e a integração da etapa 4; recarregar a sessão se necessário |
| Mapa não reflete mudanças de colegas | Executar `graphify update .` após pull/merge |
| Hooks deixaram de funcionar após atualização | Reexecutar `graphify hook install` e verificar o status |
| Aviso de redução ou extração incompleta | Investigar o motivo; não apagar o mapa nem forçar a substituição sem revisão |
| Solicitação de chave de API | Conferir se foi usado `--code-only` na primeira extração e se o escopo foi preservado |
| Falta de permissão ou senha administrativa | Parar e solicitar a ação manual necessária; não pedir segredos no chat |

## Referências oficiais

- [Repositório e documentação atual](https://github.com/Graphify-Labs/graphify).
- [Versão da documentação consultada](https://github.com/Graphify-Labs/graphify/blob/c9f99018774e2e0380e9f65b3959944559a0d5f6/README.md).
- [Instalação](https://github.com/Graphify-Labs/graphify#install).
- [Integrações com assistentes](https://github.com/Graphify-Labs/graphify#make-your-assistant-always-use-the-graph).
- [Uso em equipe](https://github.com/Graphify-Labs/graphify#team-setup).
- [Privacidade](https://github.com/Graphify-Labs/graphify#privacy).

O script Windows anteriormente criado (`scripts/configurar-graphify.ps1`) continua
disponível como opção, mas **não é necessário para seguir este guia**.

## Validacao inicial e limites

Em 2026-09-07, sobre o codigo da revisao
`87e9c8052644199387d6d7c5bb9cde992195878d`:

- 60 arquivos Python, aproximadamente 57.066 palavras.
- 951 nos, 1.647 arestas e 49 comunidades; grafo nao direcionado (padrao da skill).
- 0 tokens de entrada/saida de LLM na extracao; isto nao contabiliza o chat do Copilot.
- Diagnostico **antes** da construcao: 205 arestas com destino nao resolvido,
  0 com campo de destino ausente, 2 autorrelacoes e 36 relacoes paralelas
  sujeitas a colapso no grafo simples. Esses avisos sao limitacoes do extrator,
  nao erros comprovados na aplicacao.
- O diagnostico do JSON final nao recupera relacoes perdidas anteriormente.
  Nao conclua que dois modulos sao independentes apenas por falta de uma aresta.
- A estimativa do benchmark do Graphify foi de reducao de 7,3 vezes no contexto
  medio consultado. Nao e medicao de economia real de tokens do Copilot.
- Validacoes executadas: script PowerShell completo e sintaxe; reinstalacao
  idempotente sem mudar as instrucoes; status dos hooks; atualizacao sem mudanca
  de topologia; consulta e caminho entre ambiente/bateria; integridade dos
  endpoints do JSON final; caminhos relativos; links e frontmatter da skill;
  exclusao de arquivos locais pelo Git. O HTML foi aberto no navegador integrado.

Nao foram executados treinos nem testes da aplicacao para construir o mapa.
Uma mudanca futura no codigo deve executar os testes afetados no ambiente do
SmartEnergy, conforme o guia principal (`README.md#testes`).