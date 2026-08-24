"""Página do LLM-juiz — roda o loop agêntico (Ollama ↔ tools MCP) ao vivo.

O dashboard continua sendo um cliente MCP puro: o juiz roda AQUI (no processo
do Streamlit), chamando as mesmas ferramentas do servidor que as outras
páginas usam. O modelo (Qwen3 via Ollama) decide quais tools chamar; cada
passo é renderizado em tempo real.
"""

import json
import sys
from pathlib import Path

import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import require_setup, sincronizar_status
from smarty_energy.mcp.judge_core import (
    DEFAULT_MAX_STEPS,
    DEFAULT_MODEL,
    GOAL_DEFAULT,
    OLLAMA_BASE_URL,
    ollama_disponivel,
    run_judge_sync,
)

st.title("LLM-juiz")
st.caption(
    "O modelo (via Ollama) audita a política IQL chamando as ferramentas do "
    "servidor MCP por conta própria: treina, avalia, compara e emite um veredito. "
    "Cada chamada de ferramenta aparece abaixo em tempo real."
)

if not require_setup():
    st.stop()

ss = st.session_state
ss.setdefault("judge_historico", [])   # lista de execuções: {"goal", "eventos", "veredito"}
ss.setdefault("judge_rodando", False)

# ── Pré-requisito: Ollama ──────────────────────────────────────────────────

ok, detalhe = ollama_disponivel()
(st.success if ok else st.error)(detalhe)
if not ok:
    st.info(
        "Suba o Ollama com o modelo do juiz antes de usar esta página, ex.: "
        "`ollama run qwen3:30b` (ou ajuste as variáveis OLLAMA_BASE_URL / JUDGE_MODEL)."
    )
    st.stop()

# ── Configuração da execução ───────────────────────────────────────────────

EXEMPLOS = {
    "Auditoria padrão": GOAL_DEFAULT,
    "Auditar sem retreinar": (
        "NÃO retreine. Chame health_report, get_battery_dispatch_stats, "
        "get_hourly_violations e get_peak_offpeak_stats (agente='rl_llm_mcp') e "
        "emita um veredito sobre a política atual, comparando com o RL padrão."
    ),
    "Intervir na política": (
        "Diagnostique a política atual com as tools de métrica, ajuste os pesos "
        "do reward via configure_reward_weights com justificativa baseada em "
        "evidências, retreine com train_agents e compare com compare_strategies. "
        "Emita o veredito com os números antes/depois."
    ),
}

# Fora do form: mudar o exemplo precisa rerodar para atualizar o textarea
# (dentro de st.form as interações só são processadas no submit).
exemplo = st.selectbox("Modelos de objetivo", list(EXEMPLOS.keys()))

with st.form("judge_form"):
    goal = st.text_area(
        "Objetivo para o juiz",
        value=EXEMPLOS[exemplo],
        height=140,
        help="Instrução em linguagem natural. O modelo decide quais tools MCP chamar.",
    )
    col_a, col_b = st.columns(2)
    max_steps = col_a.number_input("Máximo de passos (rodadas de tool-call)", 4, 64,
                                   DEFAULT_MAX_STEPS)
    col_b.text_input("Modelo", DEFAULT_MODEL, disabled=True,
                     help="Definido pela variável de ambiente JUDGE_MODEL.")
    submitted = st.form_submit_button("Executar o juiz", type="primary",
                                      disabled=ss.judge_rodando)

st.warning(
    "Se o objetivo incluir retreino (`train_agents`), a execução pode levar vários "
    "minutos e a página fica ocupada até o fim. O braço **RL padrão** travado no "
    "servidor não é sobrescrito.",
    icon="⏳",
)

# ── Execução ao vivo ───────────────────────────────────────────────────────

if submitted:
    ss.judge_rodando = True
    eventos: list[dict] = []
    st.subheader("Execução ao vivo")
    status_box = st.status("Conectando ao servidor MCP...", expanded=True)

    def on_event(e: dict) -> None:
        eventos.append(e)
        if e["tipo"] == "inicio":
            status_box.update(label=f"Juiz rodando — {e['n_tools']} tools expostas ao {e['model']}")
        elif e["tipo"] == "tool_call":
            status_box.write(f"**passo {e['passo']}** → `{e['nome']}` "
                             f"`{json.dumps(e['args'], ensure_ascii=False)}`")
        elif e["tipo"] == "tool_result":
            with status_box:
                with st.expander(f"resultado de `{e['nome']}` (passo {e['passo']})"):
                    st.code(e["conteudo"][:3000], language="json")

    try:
        veredito = run_judge_sync(goal, on_event, max_steps=int(max_steps))
        status_box.update(label="Execução concluída", state="complete", expanded=False)
    except Exception as e:  # noqa: BLE001 — exibe qualquer falha (Ollama, MCP, JSON)
        status_box.update(label="Falha na execução", state="error")
        st.error(f"{type(e).__name__}: {e}")
        veredito = None
    finally:
        ss.judge_rodando = False

    ss.judge_historico.append({"goal": goal, "eventos": eventos, "veredito": veredito})
    try:
        sincronizar_status()   # o juiz pode ter treinado/comparado — reflete nas outras páginas
    except Exception:  # noqa: BLE001 — não derruba a página por falha de sync
        pass

    if veredito:
        st.subheader("Veredito do juiz")
        st.markdown(veredito)
    else:
        st.warning("O juiz atingiu o limite de passos sem emitir veredito final. "
                   "Aumente o máximo de passos ou simplifique o objetivo.")

# ── Histórico da sessão ────────────────────────────────────────────────────

if ss.judge_historico:
    st.divider()
    st.subheader("Execuções anteriores nesta sessão")
    for i, run in enumerate(reversed(ss.judge_historico), 1):
        n_calls = sum(1 for e in run["eventos"] if e["tipo"] == "tool_call")
        with st.expander(f"Execução {len(ss.judge_historico) - i + 1} — "
                         f"{n_calls} tool calls — "
                         f"{'com veredito' if run['veredito'] else 'sem veredito'}"):
            st.caption(f"Objetivo: {run['goal']}")
            for e in run["eventos"]:
                if e["tipo"] == "tool_call":
                    st.markdown(f"- passo {e['passo']}: `{e['nome']}` "
                                f"`{json.dumps(e['args'], ensure_ascii=False)}`")
            if run["veredito"]:
                st.markdown(run["veredito"])
