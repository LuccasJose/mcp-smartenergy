"""LLM-as-a-judge local usando Qwen3 (via Ollama, em GPU) sobre o servidor MCP.

Este script é um CLIENTE MCP agêntico: conecta ao `server.py` (streamable-http),
expõe TODAS as ferramentas do servidor para o modelo Qwen3 servido pelo Ollama e
deixa o modelo decidir quais tools chamar para treinar, avaliar e AUDITAR a
política IQL — emitindo ao final um veredito em linguagem natural.

Diferente do dashboard (que só renderiza payloads), aqui o LLM é o "juiz":
ele orquestra as chamadas e raciocina sobre os resultados.

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
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from openai import OpenAI

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
MODEL = os.getenv("JUDGE_MODEL", "qwen3:30b")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
MAX_STEPS = int(os.getenv("JUDGE_MAX_STEPS", "16"))

# Client OpenAI apontado para o Ollama local (API compatível com OpenAI).
client = OpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)

# Corta payloads de tool muito grandes antes de devolver ao modelo, para não
# estourar a janela de contexto (séries de TD-error podem ter milhares de pontos).
MAX_TOOL_CHARS = int(os.getenv("JUDGE_MAX_TOOL_CHARS", "6000"))

SYSTEM_PROMPT = """\
Você é um LLM-as-a-judge que audita um sistema multi-agente de gestão energética \
(IQL — Independent Q-Learning, 3 agentes cooperativos) para a fazenda FAZ-002.

Você opera EXCLUSIVAMENTE através das ferramentas MCP disponíveis — nunca invente \
números. Para emitir um veredito confiável você normalmente:
  1. chama `describe_schema` e `get_dataset_info` para entender o domínio;
  2. treina com `train_agents` (se ainda não houver treino) e avalia com \
`evaluate_agents` ou `compare_strategies`;
  3. chama `health_report` para o diagnóstico consolidado (cobertura, TD-error, \
comparação com baselines, alertas);
  4. inspeciona sinais suspeitos com as tools de métrica \
(`get_learning_curve`, `get_hourly_violations`, `get_peak_offpeak_stats`).

Reaja aos ALERTAS do health_report. Ao final, escreva um VEREDITO objetivo em \
português com: (a) a política aprendida é melhor que os baselines? em quanto %; \
(b) convergiu? (TD-error/cobertura); (c) violou restrições físicas (PCC/SOC)?; \
(d) recomendações práticas. Seja conciso e baseado em evidências das tools.\
"""


def _chat(messages: list[dict], tools: list[dict]):
    """Uma rodada de chat com o Qwen3 via client OpenAI. Retorna a message do assistant."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        temperature=0.2,
    )
    return resp.choices[0].message


def _mcp_tools_to_ollama(tool_list) -> list[dict]:
    """Converte o schema das tools MCP para o formato de function-calling do modelo."""
    tools = []
    for t in tool_list:
        schema = t.inputSchema or {"type": "object", "properties": {}}
        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": (t.description or "").strip(),
                "parameters": schema,
            },
        })
    return tools


def _extract_text(result) -> str:
    """Concatena o texto de um CallToolResult e trunca se for gigante."""
    parts = [getattr(c, "text", str(c)) for c in result.content]
    text = "\n".join(parts)
    if len(text) > MAX_TOOL_CHARS:
        text = text[:MAX_TOOL_CHARS] + f"\n...[truncado: {len(text) - MAX_TOOL_CHARS} chars omitidos]"
    return text


async def run_judge(user_goal: str) -> None:
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = (await session.list_tools()).tools
            tools = _mcp_tools_to_ollama(tool_list)
            print(f"[judge] {len(tools)} ferramentas MCP disponíveis; modelo={MODEL} @ {OLLAMA_BASE_URL}\n", file=sys.stderr)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_goal},
            ]

            for step in range(1, MAX_STEPS + 1):
                msg = _chat(messages, tools)
                calls = msg.tool_calls or []

                # Reanexa a mensagem do assistant preservando os tool_calls.
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.function.name, "arguments": c.function.arguments}}
                        for c in calls
                    ] or None,
                })

                if not calls:
                    print("\n===== VEREDITO DO JUIZ (Qwen3) =====\n")
                    print((msg.content or "").strip())
                    return

                for call in calls:
                    fn = call.function.name
                    raw = call.function.arguments or "{}"
                    args = json.loads(raw) if isinstance(raw, str) else raw
                    print(f"[judge] passo {step}: chamando {fn}({json.dumps(args, ensure_ascii=False)})", file=sys.stderr)
                    try:
                        result = await session.call_tool(fn, arguments=args)
                        content = _extract_text(result)
                    except Exception as e:  # noqa: BLE001 — devolve o erro ao modelo p/ ele reagir
                        content = json.dumps({"erro": f"{type(e).__name__}: {e}"})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": content,
                    })

            print("\n[judge] limite de passos atingido sem veredito final.", file=sys.stderr)
            print("Última mensagem do modelo:\n", (messages[-1].get("content") or "").strip())


def main() -> None:
    goal = " ".join(sys.argv[1:]).strip() or (
        "Audite o sistema IQL do zero: treine ~200 episódios, compare com os "
        "baselines, leia o health_report e emita um veredito sobre a qualidade "
        "da política aprendida."
    )
    asyncio.run(run_judge(goal))


if __name__ == "__main__":
    main()
