"""Página Overview — health_report renderizado em cards.

Reproduz visualmente o veredito que um LLM-juiz veria via `health_report`.
Toda a página é construída a partir de DUAS chamadas MCP (health_report +
get_dataset_info) — nenhum cálculo de métrica acontece no dashboard.
"""

import sys
from pathlib import Path

import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import require_setup, health_report, get_dataset_info, MCPServerError

st.title("Overview — Veredito do LLM-juiz")
st.caption("Cobertura, convergência e comparação com baselines em um só painel — via MCP.")

if not require_setup():
    st.stop()

try:
    hr = health_report()
    dataset = get_dataset_info()
except MCPServerError as e:
    st.error(str(e))
    st.stop()

# ── Dataset ────────────────────────────────────────────────────────────────
st.subheader("Dataset")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fazenda", hr["dataset"]["fazenda"])
c2.metric("Dias", hr["dataset"]["n_dias"])
c3.metric("SOC propagado", f"{hr['soc_propagado_pct']:.1f} %")
c4.metric("Horas de pico", str(dataset.get("horas_pico", "-")))

st.divider()

# ── Agentes IQL ────────────────────────────────────────────────────────────
st.subheader("Q-tables (3 agentes IQL)")
for nome, info in hr["agentes"].items():
    cob_pct = hr["cobertura_pct"][nome]
    with st.container(border=True):
        cols = st.columns(5)
        cols[0].markdown(f"**{nome}**")
        cols[1].metric("Estados visitados", info["n_estados_visitados"])
        cols[2].metric("Cobertura", f"{cob_pct:.1f} %")
        cols[3].metric("n_updates", info["n_updates"])
        cols[4].metric("TD-error |médio|",
                        f"{info['td_error_recente']['td_abs_medio']:.2f}")
        cols[0].caption(f"epsilon = {info['epsilon']:.3f}")

st.divider()

# ── Treino ─────────────────────────────────────────────────────────────────
st.subheader("Treino")
treino = hr["treino"]
if "n_episodios" in treino:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episódios", treino["n_episodios"])
    c2.metric("Reward médio (últimos 50)",
                f"{treino['reward_media_ultimos_50']:.2f}")
    c3.metric("Custo médio (últimos 50)",
                f"R${treino['custo_medio_ultimos_50_rs']:.2f}")
    c4.metric("Epsilon final", f"{treino['epsilon_final']:.3f}")
else:
    st.info("Sem treino registrado. Use a sidebar para treinar.")

st.divider()

# ── Avaliacao ─────────────────────────────────────────────────────────────
st.subheader("Avaliação atual (iql_eval)")
eval_m = hr["avaliacao_atual"]
if "n_dias" in eval_m:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dias", eval_m["n_dias"])
    c2.metric("Custo médio", f"R${eval_m['custo_medio_dia_rs']:.2f}/dia")
    c3.metric("Rede média", f"{eval_m['rede_media_dia_kwh']:.0f} kWh/dia")
    c4.metric("Violações PCC", eval_m.get("violacoes_pcc_total", 0))
    c5_, c6_, c7_, c8_ = st.columns(4)
    c5_.metric("Violações SOC", eval_m.get("violacoes_soc_total_h", 0))
    c6_.metric("kWh cortado", f"{eval_m.get('kwh_cortado_total', 0):.0f}")
    c7_.metric("Reward médio", f"{eval_m['reward_medio_dia']:.2f}")
    c8_.metric("Std custo", f"R${eval_m.get('custo_std_rs', 0):.2f}")
else:
    st.info("Sem avaliação registrada. Use 'Avaliar' na sidebar.")

st.divider()

# ── Comparacao com baselines ───────────────────────────────────────────────
st.subheader("Comparação entre estratégias")
comparacao = hr.get("comparacao_baselines")

if comparacao:
    c_iql = comparacao["custo_iql_rs_dia"]
    c_heur = comparacao["custo_heuristico_rs_dia"]
    c_sem = comparacao["custo_sem_agente_rs_dia"]
    c_puro = comparacao.get("custo_rl_puro_rs_dia")

    # Ordem narrativa: do pior cenário (sem otimização) ao melhor (RL + juiz)
    barras = [("Sem otimização", c_sem), ("Heurísticas", c_heur)]
    if c_puro is not None:
        barras.append(("RL puro", c_puro))
    barras.append(("RL + LLM-juiz", c_iql))

    cols = st.columns(len(barras))
    for col, (nome, custo) in zip(cols, barras):
        col.metric(nome, f"R${custo:.2f}/dia",
                    f"{(custo - c_sem):+.2f} vs sem otim." if nome != "Sem otimização" else None,
                    delta_color="inverse")

    reducoes = [
        f"**Redução RL vs Sem otimização:** {comparacao.get('reducao_iql_vs_sem_pct', 0):.2f} %",
        f"**vs Heurísticas:** {comparacao.get('reducao_iql_vs_heur_pct', 0):.2f} %",
    ]
    if comparacao.get("reducao_juiz_vs_rl_puro_pct") is not None:
        reducoes.append(f"**Juiz vs RL puro:** {comparacao['reducao_juiz_vs_rl_puro_pct']:.2f} %")
    st.markdown(" &nbsp;&nbsp; ".join(reducoes))

    import plotly.graph_objects as go
    fig = go.Figure(go.Bar(
        x=[n for n, _ in barras],
        y=[v for _, v in barras],
        text=[f"R${v:.2f}" for _, v in barras],
        textposition="outside",
        marker_color=["rgb(214,39,40)", "rgb(255,127,14)",
                       "rgb(31,119,180)", "rgb(44,160,44)"][:len(barras)],
    ))
    fig.update_layout(yaxis_title="Custo médio (R$/dia)",
                       margin=dict(t=10, b=30), height=350)
    st.plotly_chart(fig, use_container_width=True)

    if c_puro is None:
        st.caption("Braço 'RL puro' ausente — congele a política (botão na "
                    "sidebar ou tool snapshot_policy) antes do LLM-juiz e "
                    "rode Comparar de novo.")
else:
    st.info("Sem comparação. Use 'Comparar' na sidebar.")

st.divider()

# ── Alertas / Pesos modificados (ambos ja calculados pelo health_report) ──
st.subheader("Diagnostico")
alertas = hr.get("alertas", [])
if alertas:
    for a in alertas:
        st.warning(a)
else:
    st.success("Sem alertas — politica esta dentro dos limites configurados.")

pesos_mod = hr.get("pesos_reward_modificados")
if pesos_mod:
    with st.expander("Pesos do reward modificados"):
        st.json(pesos_mod)
