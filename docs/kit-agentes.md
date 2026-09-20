# Kit de desenvolvimento com agentes

Configuracao simplificada em 20/09/2026. Complementa o
[guia Graphify](desenvolvimento-ia.md). Nao altera o motor, o servidor MCP
do produto, os dados nem resultados de treino.

## Componentes

| Componente | Versao de referencia | Papel |
| --- | --- | --- |
| Graphify | 0.9.55 | Indice local de codigo, instalado separadamente |
| Context7 | Servico remoto oficial | Documentacao de bibliotecas; versao do servidor nao fixada |
| Ruff | 0.15.22 | Lint focado em erros, sem formatacao automatica |
| Hypothesis | 6.167.1 | Testes por propriedades junto ao pytest |
| pre-commit | 4.6.2 | Verificacoes rapidas antes de commits |
| coverage.py | 7.16.1 | Medicao de linhas e ramos no recorte do piloto |
| Import Linter | 2.15 | Contratos estaticos de dependencias internas, com Grimp |
| Node.js / npm | 22.23.2 / 10.9.8 | Toolchain local e CI da documentacao |
| Retype | 4.6.0 | Site gerado a partir de docs/, fixado no lockfile existente |
| SDK MCP (desenvolvimento) | 1.30.0 | API HTTP utilizada pelos testes de transporte |

Basic Memory e Spec Kit foram retirados por solicitacao do mantenedor. Nao sao
dependencias nem etapas de instalacao. As notas permanecem em `knowledge/`, lidas
diretamente em Markdown. Dados antigos em `.agent-kit/`, quando existentes,
ficam inativos e nao devem ser versionados nem reindexados automaticamente.

`ipykernel` e **desnecessario para o fluxo atual**: execucao por scripts,
testes, dashboards e MCP nao precisam de kernel Jupyter. Nao instala-lo como
parte da recuperacao do ambiente. O notebook existente fica preservado como
artefato; sua execucao interativa nao faz parte deste procedimento.

## Ambiente Python

Use a `.venv` do projeto tanto para execucao quanto para desenvolvimento.
No clone atual, ela usa Python 3.14.7 gerenciado pelo `uv`; nao e necessario
criar uma `.venv-dev` adicional. A CI continua usando Python 3.12: verificacoes
locais no Python 3.14 nao equivalem a uma validacao completa de compatibilidade.

Para reparar as dependencias de uma `.venv` existente, na raiz do clone:

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
uv pip check --python .venv/Scripts/python.exe
```

Em um clone sem ambiente, crie-o antes com `uv venv .venv --python 3.14`.
Nao recrie nem apague um ambiente existente sem revisar o que sera perdido.
Em Linux/macOS, substitua `.venv/Scripts/python.exe` por `.venv/bin/python`.

O VS Code deve usar `.venv/Scripts/python.exe` em **Python: Select Interpreter**.
Novos terminais podem ativar o ambiente automaticamente; em um terminal existente:

```powershell
. .\.venv\Scripts\Activate.ps1
```

Se a ativacao nao estiver disponivel, use sempre o caminho explicito do executavel.
Nao e necessario alterar o PATH global nem instalar o launcher `py` para isso.
As dependencias de desenvolvimento estao fixadas; as de runtime usam intervalos,
portanto este procedimento nao e um lock completo.

`requirements-dev.txt` fixa MCP 1.30.0 e o extra `dev` exige
`mcp>=1.30.0,<2.0.0`. O intervalo de runtime continua `mcp>=1.9.0,<2.0.0`:
isso nao significa que os testes novos possam ser executados com toda essa
faixa. A API `streamable_http_client` usada pelos testes nao existe no SDK 1.9.
Instale as dependencias de desenvolvimento para executar o gate; duas
regressoes conferem os manifests e a versao instalada. Nao se revalidou toda
a faixa de runtime nesta correcao.

O backend de build preexistente em `pyproject.toml` tem uma incompatibilidade
registrada na auditoria. Use `requirements-dev.txt`, nao `pip install -e .`.

## Context7

As configuracoes MCP locais estao em `.vscode/mcp.json` (VS Code), `.mcp.json`
(Claude Code/Copilot compativel) e `.codex/config.toml` (Codex). Elas contem caminhos
deste clone quando necessario e nao sao versionadas. Nao coloque chaves de API nelas.
O unico servidor auxiliar configurado e `context7`, com endpoint oficial
`https://mcp.context7.com/mcp`, sem dependencia do Python local.

No VS Code, abra **MCP: List Servers** e inicie `context7`, confirmando a confianca
quando solicitada. No Claude e no Codex, confira `/mcp`. Nao desative aprovacoes.
Abra uma nova conversa apos remover skills para nao reutilizar a lista anterior.

Envie somente biblioteca, versao instalada e perguntas genericas. Nao envie codigo
privado, dados ou caminhos da maquina. Documentacao recuperada nao comprova
compatibilidade do ambiente. Limites e requisitos do servico podem mudar.

## Notas E Planejamento

Consulte `knowledge/index.md` e apenas as notas relevantes.
Esta e a base de notas versionaveis, nao uma copia de `CONTEXT.md` ou da arquitetura.
Nao ha servidor de memoria nem indexacao automatica. Fontes externas precisam de
autorizacao antes de serem incorporadas.

O workflow (`knowledge/workflow.md`) diferencia fatos, hipoteses e decisoes.
Revise cada diff antes de versionar. Cada agente deve reler uma nota antes de
edita-la; evite escritores simultaneos. Entre clones, sincronize o Markdown pelo Git.
Nao compartilhe bancos SQLite antigos. Trechos lidos ainda podem ir ao provedor do LLM.

As regras de fisica, evidencias, privacidade e planejamento estao em
`AGENTS.md`. Mudancas relevantes exigem plano, criterios de aceitacao,
aprovacao e testes, sem depender de um gerador de especificacoes.

## Verificacoes

Na raiz do clone, sem carregar `.env` nem datasets privados:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
& .\.venv\Scripts\python.exe -m ruff check .
& .\.venv\Scripts\python.exe -m pytest tests/test_battery.py tests/test_battery_properties.py -q
& .\.venv\Scripts\python.exe -m pre_commit run --all-files
```

Para a selecao ampliada e a medicao de cobertura, siga os comandos do
[plano de reorganizacao](reorganizacao.md). A configuracao em `pyproject.toml`
mede ramos e restringe o relatorio a oito modulos inteiros do piloto; nao e
a cobertura de todo o produto. `coverage report` mostra a porcentagem combinada
de linhas e ramos. O JSON permite calcular as duas separadamente.
Os arquivos `.coverage`, `.coverage-piloto.json` e `htmlcov/` ficam fora do Git.
Nao ha limiar de aprovacao por porcentagem nesta etapa de linha de base.

### Contratos de arquitetura

Na raiz, com dependencias de desenvolvimento instaladas:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$pythonpathAnterior = $env:PYTHONPATH
try {
	$env:PYTHONPATH = (Join-Path $PWD 'src')
	& .\.venv\Scripts\lint-imports.exe --config pyproject.toml --no-cache
	if ($LASTEXITCODE -ne 0) { throw 'Contratos de imports falharam' }
} finally {
	$env:PYTHONPATH = $pythonpathAnterior
}
```

Na CI Linux, o passo usa `PYTHONPATH=src` e
`lint-imports --config pyproject.toml --no-cache`. O path e temporario: nao
instalar o pacote em modo editavel para contornar o backend de build existente.
Sem cache, nenhum artefato novo do Import Linter precisa entrar no Git.

Os quatro [contratos](arquitetura.md) verificam imports internos diretos e
indiretos. Os nove testes de arquitetura em
test_fisica_unificada.py (`tests/mcp/test_fisica_unificada.py`) usam somente
copias de arquivos Python/configuracao em tmp_path, sem executar o pacote
copiado; oito casos devem falhar no linter para o teste passar. Rodar apenas
esses testes: `python -m pytest tests/mcp/test_fisica_unificada.py -k contratos_arquitetura -q`,
com o executavel da `.venv`. A selecao completa ja os inclui.
Imports dinamicos e efeitos de inicializadores ancestrais nao sao certificados.
Mudancas nas listas de modulos precisam de revisao, nao excecoes automaticas.

### Transporte MCP sintetico

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
& .\.venv\Scripts\python.exe -m pytest tests/mcp/test_transport.py -q
```

Requer subprocessos e bind TCP em loopback. Nao requer internet, dataset,
token ou servidor previamente iniciado. Os testes reutilizam o dia e a tarifa
sinteticos, bloqueiam o loader padrao no filho e usam porta escolhida pelo SO.
HTTP usa o SDK e o cliente Python real do dashboard, nao a interface Streamlit.
Os processos encerram ao final; falha de bind/startup e erro, nao skip silencioso.
Arquivos auxiliares e logs ficam apenas no tmp_path do pytest.

Os testes verificam resultados via protocolo, mas a cobertura atual nao coleta
execucao nos processos filhos. O cliente do dashboard ainda gera avisos de
depreciacao para `streamablehttp_client`; nao foram ocultados. Ver escopo e
limitacoes no [contrato de transporte](mcp.md).

Para verificar Context7 pela rede, quando necessario:

```powershell
& .\.venv\Scripts\python.exe scripts/verificar_mcp_kit.py --context7
```

O script requer Python 3.11+ e o SDK MCP 1.x de `requirements-dev.txt`.
`--client claude` ou `--client codex` escolhe outro arquivo de configuracao.
`--context7` faz chamadas somente sobre documentacao publica de NumPy,
sem LLM-juiz ou treino; nao e parte obrigatoria da validacao offline.

Ruff usa apenas E9, F63, F7 e F82 inicialmente. Os testes novos verificam conservacao
AC/DC, limites de SoC e throughput compartilhado em sequencias. Nao provam a fisica
completa do ambiente nem desempenho do RL. Nao use a suite completa ou apenas
`-m 'not slow'` como verificacao rapida, pois ha fixtures que treinam sem essa marca.

## Build Da Documentacao

O build requer Node 22 e npm. Neste clone foi preparada uma distribuicao
portatil oficial 22.23.2, com SHA256 conferido contra SHASUMS256.txt da mesma
versao. Nao houve instalacao como administrador nem alteracao de PATH global.
Em um novo terminal Windows deste clone, para usar essa instalacao:

```powershell
$nodeDir = Join-Path $env:LOCALAPPDATA 'smartenergy-tools/node-v22.23.2-win-x64'
$env:PATH = "$nodeDir;$env:PATH"
```

Com Node disponivel, execute a partir da raiz:

```powershell
npm.cmd --prefix docs ci --no-audit --no-fund
npm.cmd --prefix docs run docs:test
npm.cmd --prefix docs run docs:build
& .\.venv\Scripts\python.exe scripts/verificar_docs.py
```

Em Linux/macOS use `npm` e o Python do ambiente correto. O verificador usa
somente biblioteca padrao, sem importar o motor. O lockfile existente fixa
Retype 4.6.0; nao e necessario atualizar pacotes para reproduzir o build.
O preview chama o wrapper Node do Retype diretamente, porque nesta instalacao
o atalho `retype` em node_modules/.bin nao foi criado. O build passa por
`scripts/build_docs.cjs`, que invoca esse mesmo wrapper e aplica o gate estrito.
`predocs:build` remove
somente `docs/site`, que e saida gerada e nunca deve conter arquivos autorais.

O Retype 4.6 pode emitir avisos de YAML/template invalidos e retornar codigo 0.
O gate agora rejeita WARNING/ERROR em stdout ou stderr, contagens nao nulas,
processo interrompido/falho ou ausencia do resumo esperado de zero erros e
avisos. Preserva a saida para diagnostico e nao depende de Retype Pro. O formato
de saida corresponde ao Retype fixado no lockfile; mudancas nesse formato devem
ser revisadas ao atualizar a ferramenta, sem desativar o gate.

`docs:test` usa o runner nativo do Node: dez testes de classificacao da saida e
tres builds reais com pagina valida, frontmatter invalido e template invalido,
somente em diretorios temporarios. O teste invalido passa quando o wrapper
retorna erro. O verificador HTML permanece uma etapa complementar, pois nao
detecta todos os erros de geracao nem certifica o conteudo cientifico.

O site fica em `docs/site/index.html`. Links de navegacao incluem index.html
e o indice de busca e pre-carregado para uso por arquivo local. Referencias
a codigo, configuracao e notas fora de docs/ sao caminhos relativos a raiz
do repositorio, nao links do site: seu conteudo nao e copiado para a publicacao.
O input do Retype continua limitado a docs/. Arquivos npm sao excluidos da saida.

`scripts/verificar_docs.py` valida destinos locais de href/src e ancoras em
HTML. Nao consulta URLs externas, nao inspeciona url() dentro de CSS e nao
substitui revisao de conteudo ou teste visual completo. Os testes sinteticos
do verificador estao em `tests/test_docs.py`.

A URL `https://smartenergy-mas.example.com` continua sendo um placeholder:
Retype 4.6 rejeitou URL ausente e localhost. O logo e metadados canonicos usam
essa base; defini-la com o destino real e requisito antes de publicar.
`cname: false` impede gerar configuracao de dominio. Nenhum deploy e realizado.
Para preview servido, `npm.cmd --prefix docs run docs:dev -- --no-open`
inicia o servidor local quando solicitado pelo mantenedor.

A CI tem job `documentacao` com Node 22.23.2, npm ci, docs:test, build estrito e validador. Ele
nao publica artefatos. Configurar a CI nao comprova sua execucao remota.

O uso acordado e local, sem deploy. O badge opcional do cabecalho foi removido
e `docs/_includes/head.html` permite quebrar comandos inline e a marca em telas
estreitas. Nao editar CSS gerado em site/ ou node_modules/. As paginas centrais
foram verificadas em 320, 390 e 1280 px; isso nao substitui auditoria visual de
todas as paginas ou acessibilidade completa.

## Rotina Apos O Aceite

A entrega local e seus comandos finais estao em [Reorganizacao](reorganizacao.md).
Para cada mudanca, localizar a regra na matriz, conferir o codigo atual,
atualizar as duas visoes pertinentes e executar o teste do contrato afetado.
Justificativas novas entram em ADR; nao deduzir a origem de parametros fisicos.

| Mudanca representativa | Ponto de controle | Verificacao local pertinente |
|---|---|---|
| Startup ou fonte de dados | initialize, prioridade de fontes, R-DAD-001/R-MCP-002 | testes FEMS, startup e transporte sintetico |
| Estado/trace ou persistencia | ServerState, R-MCP-001/003, R-RUN-001/002 | tools, switch_dataset, experiments e runs |
| Regra/parametro/avaliacao | R-BAT/R-SOC/R-TRE e contrato de codificacao | invariantes, limites, checkpoint e paridade com pipeline; aprovacao antes de mudar o modelo |

Os tres casos sao um roteiro de verificacao, nao uma medicao de produtividade.
Antes de propor integracao, executar a selecao completa do plano, lint e
Import Linter; para documentacao, docs:test, build e verificar_docs. Revise tambem os
novos arquivos nao rastreados com `pre_commit run --files`.
Nao iniciar treino longo, juiz LLM, commit, push ou deploy automaticamente.

## Hooks E Graphify

Depois de reparar ou mover a `.venv`, reinstale o hook para atualizar seu caminho:

```powershell
& .\.venv\Scripts\python.exe -m pre_commit install
```

Os hooks nao fazem autofix. `--all-files` considera arquivos rastreados; use
`--files` para verificar arquivos novos antes de adiciona-los ao Git.
Nao substituir hooks de outros componentes. A
CI (`.github/workflows/qualidade-kit.yml`) repete lint, hooks, contratos de imports e a selecao do
piloto sob coverage.py em Python 3.12. Usa dados sinteticos, o teste de treino
de tres episodios e as chamadas de dois episodios dos testes MCP, sem dados
privados ou treinos longos. Inclui dois testes de transporte real em processos
isolados, com HTTP restrito a loopback e portas efemeras; nao acessa rede externa.

Graphify permanece separado da `.venv`; a recuperacao das dependencias do produto
nao reinstala essa ferramenta. Para instala-lo ou reparar seus hooks, siga o
[guia Graphify](desenvolvimento-ia.md). Preserve o escopo de `.graphifyignore`.
Nao versionar configuracoes pessoais MCP, caches, bancos, logs ou caminhos locais.

## Fontes oficiais

- [Context7](https://github.com/upstash/context7)
- [Skills no VS Code](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [MCP no VS Code](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [MCP no Codex](https://developers.openai.com/codex/mcp)
- [Memoria no Claude Code](https://code.claude.com/docs/en/memory)
- [Ruff](https://docs.astral.sh/ruff/), [Hypothesis](https://hypothesis.readthedocs.io/), [pre-commit](https://pre-commit.com/)
- [coverage.py 7.16.1](https://coverage.readthedocs.io/en/7.16.1/), [configuracao](https://coverage.readthedocs.io/en/7.16.1/config.html)
- [Import Linter](https://import-linter.readthedocs.io/en/stable/), [contratos forbidden](https://import-linter.readthedocs.io/en/stable/contract_types/forbidden/), [Grimp](https://grimp.readthedocs.io/en/stable/usage.html)
- [SDK MCP 1.30.0: clientes](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/docs/client.md)
- [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)