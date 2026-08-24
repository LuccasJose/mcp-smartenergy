"""LLM-as-a-judge local usando Qwen3 (via Ollama, em GPU) sobre o servidor MCP.

CLI fino sobre `smarty_energy.mcp.judge_core` — a mesma implementação usada
pela página "LLM-juiz" do dashboard Streamlit. O juiz é um CLIENTE MCP
agêntico: conecta ao `server.py` (streamable-http), expõe TODAS as ferramentas
do servidor ao modelo e deixa o modelo decidir quais tools chamar para treinar,
avaliar e AUDITAR a política IQL — emitindo ao final um veredito em linguagem
natural.

Pré-requisitos
--------------
1. Ollama rodando (em GPU) com o modelo `qwen3:30b`.
   Expõe uma API compatível com OpenAI em `http://127.0.0.1:11434/v1`.
2. Servidor MCP rodando à parte:   `python server.py`

Uso
---
    .venv/bin/python judge.py
    .venv/bin/python judge.py "Treine 300 episódios, compare com baselines e diga se a política presta"

Variáveis de ambiente (todas opcionais)
--------------------------------------
    OLLAMA_BASE_URL  (default http://127.0.0.1:11434/v1)  — base_url do client OpenAI
    OLLAMA_API_KEY   (default ollama)                     — chave dummy exigida pelo SDK
    JUDGE_MODEL      (default qwen3:30b)
    MCP_SERVER_URL   (default http://127.0.0.1:8000/mcp)
    JUDGE_MAX_STEPS  (default 16)  — nº máximo de rodadas de tool-call
    JUDGE_MAX_TOOL_CHARS (default 6000) — truncagem de payloads de tool
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from smarty_energy.mcp.judge_core import (
    GOAL_DEFAULT,
    OLLAMA_BASE_URL,
    run_judge_sync,
)


def _on_event(e: dict) -> None:
    if e["tipo"] == "inicio":
        print(f"[judge] {e['n_tools']} ferramentas MCP disponíveis; "
              f"modelo={e['model']} @ {OLLAMA_BASE_URL}\n", file=sys.stderr)
    elif e["tipo"] == "tool_call":
        print(f"[judge] passo {e['passo']}: chamando "
              f"{e['nome']}({json.dumps(e['args'], ensure_ascii=False)})", file=sys.stderr)
    elif e["tipo"] == "veredito":
        print("\n===== VEREDITO DO JUIZ =====\n")
        print(e["texto"])
    elif e["tipo"] == "limite":
        print("\n[judge] limite de passos atingido sem veredito final.", file=sys.stderr)
        print("Última mensagem do modelo:\n", e["ultima_msg"])


def main() -> None:
    goal = " ".join(sys.argv[1:]).strip() or GOAL_DEFAULT
    run_judge_sync(goal, _on_event)


if __name__ == "__main__":
    main()
