---
label: Execução do MCP
icon: terminal
order: 25
---

# Como inicializar o servidor MCP

Dois processos, dois terminais, nessa ordem: **servidor primeiro, dashboard
depois**. Para arquitetura, ferramentas e reward, veja [Servidor MCP](mcp.md).

---

## 0. Uma vez só: instalar dependências

Abra um terminal PowerShell **na raiz do projeto** (a pasta que tem `main.py`
e `server.py`):

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use sempre `.venv\Scripts\python.exe` (não o `python`/`pip` do sistema) —
instalar no Python global pode conflitar com outros projetos.

O mesmo ambiente serve para o pipeline offline (`main.py`) e para o servidor:
as dependências já estão unificadas em `requirements.txt`.

---

## 1. Terminal 1 — subir o servidor MCP

```powershell
.venv\Scripts\python.exe server.py
```

O comando inicializa o estado antes de abrir o transporte. Exemplo de saída
com Sheets configurado (a fonte e o número de dias dependem da configuração;
o processo **fica rodando**, não feche este terminal):

```
Carregando dataset...
  Baixando planilha do Google Drive...
  31 dias carregados (fazenda FAZ-002).
Servidor MCP em http://127.0.0.1:8000/mcp (transporte streamable-http)
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Uso por código Python

Quem usa o ponto de entrada acima não precisa mudar nada. Para chamar funções
diretamente, inicialize o módulo antes de acessar dados ou tools:

```python
from smarty_energy.mcp import server

server.initialize()
informacoes = server.get_dataset_info()
```

Esse exemplo pressupõe o pacote importável, como no ponto de entrada da raiz,
e carrega a fonte configurada. Em testes, use `initialize(loader=...)` com
dados sintéticos. A importação não carrega o dataset. Uma segunda chamada
de initialize não reinicia a sessão; falha de carga impede o startup.
`server.main()` já inicializa e inicia o transporte; se usar `server.mcp.run()`
diretamente, a inicialização prévia é responsabilidade do chamador.

Código Python interno que inspecionava `server.DIAS`, `server.env` ou
`server.iql` deve usar `server.get_state().dias`, `.env` ou `.iql` após
inicializar. Os antigos atributos não são mantidos como aliases. `get_state()`
retorna o objeto ativo mutável, não uma cópia nem uma sessão por cliente;
prefira as tools para comandos e consultas normais. Nenhuma tool ou argumento
do protocolo MCP foi renomeado nesta migração.

---

## 2. Terminal 2 — subir o dashboard

Abra um **segundo** terminal (o primeiro precisa continuar rodando):

```powershell
.venv\Scripts\python.exe -m streamlit run src\smarty_energy\mcp\dashboard\app.py
```

Abre automaticamente `http://localhost:8501` no navegador. Na sidebar, clique
em **Conectar** — isso confirma que o dashboard achou o servidor do Terminal 1.
O fluxo legado está em **Executar análise**. O protocolo com conjuntos separados
está em [Divisões do dataset](divisoes-dataset.md); seus resultados são isolados
da política ativa.

### Descrições e ajuda contextual

Todas as páginas têm uma seção expansível de conceitos e critérios, disponível
mesmo sem conexão ao MCP. Os campos e comandos relevantes incluem ajuda contextual
sobre valores, unidades, efeitos no estado e limites de interpretação.

| Página | Conteúdo das descrições |
| --- | --- |
| Início | Dataset, política ativa, experimentos isolados, unidades e estado compartilhado |
| Executar análise | Run versus par de políticas, orçamento por treino, persistência e avaliação legada |
| Visão geral | Custo, economia, baselines, reward, cobertura e limites dos alertas |
| Curva de aprendizado | Episódios, epsilon, média móvel, erro TD e generalização |
| Trace diário | Ação solicitada versus fluxo, aprendizado online e SoC entre simulações |
| Equipamentos | Potência versus energia, custo bruto por carga, médias e bloqueios da bateria |
| LLM-juiz | Intenção de cada objetivo, autonomia das ferramentas, passos, custos e privacidade |
| Fazendas FEMS | Cadastro, geração, seed dos dados, período e efeitos de ativar outra base |
| Divisões do dataset | Cinco protocolos, proporções, cortes mensais fixos, seeds, blocos, validação e teste final |

A descrição do juiz não depende de `openai` ou de Ollama disponíveis; a execução
do juiz continua exigindo suas dependências e serviço. O objetivo “sem retreinar”
é uma instrução ao modelo, não uma restrição técnica às ferramentas.

As descrições não alteram o motor: exploração no trace da política viva continua
atualizando as Q-tables, e a avaliação legada não ganha um holdout automaticamente.

!!!tip Aproveitar um treino longo
Em vez de treinar pelo dashboard, chame a tool `load_qtables()` para carregar
o run mais recente de `outputs/runs/` — inclusive um treinado por
`python main.py` com 100.000 episódios.
!!!

---

## 3. Checklist se algo não abrir

- **Rodou os dois comandos da raiz do projeto?** (a pasta com `server.py` e `main.py`)
- **Usou `.venv\Scripts\python.exe` nos dois terminais?** (não `python` puro)
- **O Terminal 1 (servidor) ainda está aberto e sem erro?** O dashboard depende dele — sem ele, "Conectar" falha.
- **Porta 8000 já em uso?** Se o servidor reclamar disso, outro `server.py` já está rodando — reaproveite-o ou feche o antigo. Para trocar de porta: `$env:MCP_PORT = "8010"`.
- **Sem internet?** Use FEMS local ou desative `FEMS_DATASET_DIR` e `SHEET_ID` para usar o Excel definido em `DATA_PATH`. A [prioridade das fontes](dados.md) também vale no startup explícito; não há fallback automático.
