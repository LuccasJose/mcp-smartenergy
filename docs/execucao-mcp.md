# Manual — Como Inicializar o MCP SmartEnergy

Dois processos, dois terminais, nessa ordem: **servidor primeiro,
dashboard depois**. Para arquitetura/ferramentas/reward, veja o
[README.md](README.md).

---

## 0. Uma vez só: instalar dependências

Abra um terminal PowerShell **dentro da pasta `mcp-smartenergy\`**
(a que tem `server.py` e `dashboard\` — não a pasta pai):

```powershell
cd "C:\Users\lucca\OneDrive\Desktop\mcpsmartenergy\mcp-smartenergy"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use sempre `.venv\Scripts\python.exe` (não o `python`/`pip` do sistema) —
instalar no Python global pode conflitar com outros projetos que você
já tem instalados nele.

---

## 1. Terminal 1 — subir o servidor MCP

```powershell
cd "C:\Users\lucca\OneDrive\Desktop\mcpsmartenergy\mcp-smartenergy"
.venv\Scripts\python.exe server.py
```

Saída esperada (o processo **fica rodando**, não feche este terminal):

```
Baixando dataset do Google Sheets...
  31 dias carregados (fazenda FAZ-002).
Servidor MCP em http://127.0.0.1:8000/mcp (transporte streamable-http)
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## 2. Terminal 2 — subir o dashboard

Abra um **segundo** terminal (o primeiro precisa continuar rodando):

```powershell
cd "C:\Users\lucca\OneDrive\Desktop\mcpsmartenergy\mcp-smartenergy"
.venv\Scripts\python.exe -m streamlit run dashboard\app.py
```

Abre automaticamente `http://localhost:8501` no navegador. Na sidebar,
clique em **Conectar** — isso confirma que o dashboard achou o servidor
do Terminal 1. Depois é só usar **Treinar IQL**, **Avaliar** e
**Comparar**.

---

## 3. Checklist se algo não abrir

- **Rodou os dois comandos de dentro de `mcp-smartenergy\`?** (não da pasta pai `mcpsmartenergy\`)
- **Usou `.venv\Scripts\python.exe` nos dois terminais?** (não `python` puro)
- **O Terminal 1 (servidor) ainda está aberto e sem erro?** O dashboard depende dele — sem ele, "Conectar" falha.
- **Porta 8000 já em uso?** Se o servidor reclamar disso, outro `server.py` já está rodando — reaproveite-o ou feche o antigo antes de subir outro.
