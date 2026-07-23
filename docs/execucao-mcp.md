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

Saída esperada (o processo **fica rodando**, não feche este terminal):

```
Carregando dataset...
  Baixando planilha do Google Drive...
  31 dias carregados (fazenda FAZ-002).
Servidor MCP em http://127.0.0.1:8000/mcp (transporte streamable-http)
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## 2. Terminal 2 — subir o dashboard

Abra um **segundo** terminal (o primeiro precisa continuar rodando):

```powershell
.venv\Scripts\python.exe -m streamlit run src\smarty_energy\mcp\dashboard\app.py
```

Abre automaticamente `http://localhost:8501` no navegador. Na sidebar, clique
em **Conectar** — isso confirma que o dashboard achou o servidor do Terminal 1.
Depois é só usar **Treinar IQL**, **Avaliar** e **Comparar**.

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
- **Sem internet?** O servidor baixa a base no startup. Aponte `DATA_PATH` para o Excel local e deixe `SHEET_ID` vazio no `.env`.
