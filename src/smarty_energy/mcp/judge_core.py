"""Loop do LLM-as-a-judge, reutilizável pelo CLI (`judge.py`) e pelo dashboard.

O juiz é um CLIENTE MCP agêntico: conecta ao servidor (`server.py`), expõe
todas as ferramentas ao modelo servido pelo Ollama (API compatível com OpenAI)
e deixa o modelo orquestrar as chamadas — treinar, avaliar e auditar a política
IQL — emitindo ao final um veredito em linguagem natural.

Eventos são reportados via callback `on_event(dict)`, o que permite tanto
imprimir no stderr (CLI) quanto renderizar ao vivo no Streamlit.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Callable

from openai import OpenAI

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
DEFAULT_MODEL = os.getenv("JUDGE_MODEL", "qwen3:30b")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
DEFAULT_MAX_STEPS = int(os.getenv("JUDGE_MAX_STEPS", "16"))

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

GOAL_DEFAULT = (
    "Audite o sistema IQL do zero: treine ~200 episódios, compare com os "
    "baselines, leia o health_report e emita um veredito sobre a qualidade "
    "da política aprendida."
)


def _mcp_tools_to_openai(tool_list) -> list[dict]:
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


async def run_judge(
    user_goal: str,
    on_event: Callable[[dict], None] | None = None,
    *,
    model: str = DEFAULT_MODEL,
    max_steps: int = DEFAULT_MAX_STEPS,
    base_url: str = OLLAMA_BASE_URL,
    server_url: str = MCP_SERVER_URL,
) -> str | None:
    """Executa o loop agêntico. Retorna o texto do veredito (ou None se
    o limite de passos foi atingido sem veredito).

    Eventos emitidos via on_event:
      {"tipo": "inicio", "n_tools": int, "model": str}
      {"tipo": "tool_call", "passo": int, "nome": str, "args": dict}
      {"tipo": "tool_result", "passo": int, "nome": str, "conteudo": str}
      {"tipo": "veredito", "texto": str}
      {"tipo": "limite", "ultima_msg": str}
    """
    emit = on_event or (lambda e: None)
    client = OpenAI(base_url=base_url, api_key=OLLAMA_API_KEY)

    def _chat(messages: list[dict], tools: list[dict]):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=tools, temperature=0.2,
        )
        return resp.choices[0].message

    async with streamablehttp_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = (await session.list_tools()).tools
            tools = _mcp_tools_to_openai(tool_list)
            emit({"tipo": "inicio", "n_tools": len(tools), "model": model})

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_goal},
            ]

            for step in range(1, max_steps + 1):
                # A chamada ao Ollama é síncrona (bloqueante); roda num thread
                # para não travar o event loop da sessão MCP.
                msg = await asyncio.to_thread(_chat, messages, tools)
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
                    veredito = (msg.content or "").strip()
                    emit({"tipo": "veredito", "texto": veredito})
                    return veredito

                for call in calls:
                    fn = call.function.name
                    raw = call.function.arguments or "{}"
                    args = json.loads(raw) if isinstance(raw, str) else raw
                    emit({"tipo": "tool_call", "passo": step, "nome": fn, "args": args})
                    try:
                        result = await session.call_tool(fn, arguments=args)
                        content = _extract_text(result)
                    except Exception as e:  # noqa: BLE001 — devolve o erro ao modelo p/ ele reagir
                        content = json.dumps({"erro": f"{type(e).__name__}: {e}"})
                    emit({"tipo": "tool_result", "passo": step, "nome": fn, "conteudo": content})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": content,
                    })

            emit({"tipo": "limite", "ultima_msg": (messages[-1].get("content") or "").strip()})
            return None


def run_judge_sync(user_goal: str, on_event: Callable[[dict], None] | None = None,
                   **kwargs) -> str | None:
    """Wrapper síncrono de `run_judge` (uso no Streamlit e em scripts simples)."""
    return asyncio.run(run_judge(user_goal, on_event, **kwargs))


def ollama_disponivel(base_url: str = OLLAMA_BASE_URL, model: str = DEFAULT_MODEL) -> tuple[bool, str]:
    """(ok, detalhe): verifica se o Ollama responde e se o modelo existe."""
    try:
        client = OpenAI(base_url=base_url, api_key=OLLAMA_API_KEY)
        ids = [m.id for m in client.models.list().data]
    except Exception as e:  # noqa: BLE001
        return False, f"Ollama inacessível em {base_url}: {e}"
    if model not in ids:
        return False, f"Modelo '{model}' não encontrado no Ollama (disponíveis: {ids})"
    return True, f"Ollama ok — modelo {model} disponível"
