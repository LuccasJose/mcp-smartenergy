---
label: Instalação
icon: download
order: 90
---

# Instalação

## Pré-requisitos

- **Python 3.10+**
- `pip` para instalar as dependências
- A base de dados Excel em `dados/modelo_gestao_energia_fazenda_v8.xlsx`

!!!warning A base não está no Git
A pasta `dados/` é ignorada pelo Git (`*.xlsx`). Mantenha uma cópia de backup
da planilha — sem ela o pipeline não roda.
!!!

## Passos

1. Clone o repositório e entre na pasta do projeto.

2. (Opcional, recomendado) crie um ambiente virtual:

   ```bash
   python -m venv .venv
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   # Linux / macOS
   source .venv/bin/activate
   ```

3. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

## Variáveis de ambiente (opcionais)

O projeto lê um arquivo `.env` na raiz (via `python-dotenv`). Todas têm padrão
sensato — defina apenas se quiser sobrescrever:

| Variável | Padrão | Descrição |
|---|---|---|
| `DATA_PATH` | `dados/modelo_gestao_energia_fazenda_v8.xlsx` | Caminho da base Excel local |
| `ID_FAZENDA` | `FAZ-002` | Fazenda usada no modelo (`FAZ-001` ou `FAZ-002`) |
| `SHEET_ID` | *(vazio)* | ID de um Google Sheets com o mesmo esquema (alternativa à base local) |
| `OUTPUT_DIR` | `outputs` | Pasta de saída de gráficos e modelos |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8000` | Endereço do servidor MCP |
| `MCP_N_EPISODIOS` | `1000` | Episódios por chamada de `train_agents` |

O mesmo `requirements.txt` cobre os dois modos de uso — não é preciso um
ambiente separado para o servidor MCP.

Com tudo instalado, siga para a [Execução](execucao.md) ou, se for usar o
LLM-juiz, para a [Execução do MCP](execucao-mcp.md).
