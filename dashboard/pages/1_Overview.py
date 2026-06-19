"""Pagina Overview — health_report renderizado em cards.

Reproduz visualmente o veredito que um LLM-juiz veria via `health_report`.
"""

import sys
from pathlib import Path

import streamlit as st

# Garante que raiz e dashboard/ estao no path quando rodado por streamlit
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashboard.state import require_setup, CONFIG, N_ESTADOS_TOTAL

st.title("Overview — Veredito do LLM-juiz")
st.caption("Cobertura, convergencia e comparacao com baselines em um so painel.")

if not require_setup():
    st.stop()

ss = st.session_state
iql = ss.iql
tracker = ss.tracker

# ── Dataset ────────────────────────────────────────────────────────────────
st.subheader("Dataset")
m = ss.meta
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fazenda", m["id_fazenda"])
c2.metric("Dias", m["n_dias"])
c3.metric("SOC propagado", f"{iql.soc_propagado:.1f} %")
c4.metric("Horas de pico", str(m["horas_pico"]))

st.divider()

# ── Agentes IQL ────────────────────────────────────────────────────────────
st.subheader("Q-tables (3 agentes IQL)")
for nome, ag in iql.agentes.items():
    info = ag.get_info()
    cob_pct = info["n_estados_visitados"] / N_ESTADOS_TOTAL * 100
    with st.container(border=True):
        cols = st.columns(5)
        cols[0].markdown(f"**{nome}**")
        cols[1].metric("Estados visitados", info["n_estados_visitados"])
        cols[2].metric("Cobertura", f"{cob_pct:.1f} %")
        cols[3].metric("n_updates", info["n_updates"])
        cols[4].metric("TD-error |medio|",
                        f"{info['td_error_recente']['td_abs_medio']:.2f}")
        cols[0].caption(f"epsilon = {info['epsilon']:.3f}")

st.divider()

# ── Treino ─────────────────────────────────────────────────────────────────
st.subheader("Treino")
treino = tracker.get_training_metrics("iql_treino")
if "n_episodios" in treino:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Episodios", treino["n_episodios"])
    c2.metric("Reward medio (ultimos 50)",
                f"{treino['reward_media_ultimos_50']:.2f}")
    c3.metric("Custo medio (ultimos 50)",
                f"R${treino['custo_medio_ultimos_50_rs']:.2f}")
    c4.metric("Epsilon final", f"{treino['epsilon_final']:.3f}")
else:
    st.info("Sem treino registrado. Use a sidebar para treinar.")

st.divider()

# ── Avaliacao ─────────────────────────────────────────────────────────────
st.subheader("Avaliacao atual (iql_eval)")
eval_m = tracker.get_eval_metrics("iql_eval")
if "n_dias" in eval_m:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dias", eval_m["n_dias"])
    c2.metric("Custo medio", f"R${eval_m['custo_medio_dia_rs']:.2f}/dia")
    c3.metric("Rede media", f"{eval_m['rede_media_dia_kwh']:.0f} kWh/dia")
    c4.metric("Violacoes PCC", eval_m.get("violacoes_pcc_total", 0))
    c5_, c6_, c7_, c8_ = st.columns(4)
    c5_.metric("Violacoes SOC", eval_m.get("violacoes_soc_total_h", 0))
    c6_.metric("kWh cortado", f"{eval_m.get('kwh_cortado_total', 0):.0f}")
    c7_.metric("Reward medio", f"{eval_m['reward_medio_dia']:.2f}")
    c8_.metric("Std custo", f"R${eval_m['custo_std_rs']:.2f}")
else:
    st.info("Sem avaliacao registrada. Use 'Avaliar' na sidebar.")

st.divider()

# ── Comparacao com baselines ───────────────────────────────────────────────
st.subheader("Comparacao com baselines")
cmp_iql = tracker.get_eval_metrics("iql_eval_cmp")
cmp_heur = tracker.get_eval_metrics("heuristico")
cmp_sem  = tracker.get_eval_metrics("sem_agente")

if all("custo_medio_dia_rs" in m for m in (cmp_iql, cmp_heur, cmp_sem)):
    c_iql = cmp_iql["custo_medio_dia_rs"]
    c_heur = cmp_heur["custo_medio_dia_rs"]
    c_sem = cmp_sem["custo_medio_dia_rs"]
    c1, c2, c3 = st.columns(3)
    c1.metric("IQL (RL)", f"R${c_iql:.2f}/dia")
    c2.metric("Heuristico", f"R${c_heur:.2f}/dia",
                f"{(c_iql - c_heur):+.2f}")
    c3.metric("SemAgente", f"R${c_sem:.2f}/dia",
                f"{(c_iql - c_sem):+.2f}")

    red_sem = (c_sem - c_iql) / c_sem * 100 if c_sem > 0 else 0
    red_heur = (c_heur - c_iql) / c_heur * 100 if c_heur > 0 else 0
    st.markdown(
        f"**Reducao IQL vs SemAgente:** {red_sem:.2f} % &nbsp;&nbsp;&nbsp; "
        f"**vs Heuristico:** {red_heur:.2f} %"
    )

    import plotly.graph_objects as go
    fig = go.Figure(go.Bar(
        x=["IQL", "Heuristico", "SemAgente"],
        y=[c_iql, c_heur, c_sem],
        text=[f"R${v:.2f}" for v in (c_iql, c_heur, c_sem)],
        textposition="outside",
    ))
    fig.update_layout(yaxis_title="Custo medio (R$/dia)",
                       margin=dict(t=10, b=30), height=350)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem comparacao. Use 'Comparar' na sidebar.")

st.divider()

# ── Alertas / Pesos modificados ────────────────────────────────────────────
from server import _DEFAULT_REWARD_WEIGHTS, _REWARD_WEIGHT_KEYS  # noqa: E402

pesos_mod = {k: {"atual": CONFIG[k], "default": _DEFAULT_REWARD_WEIGHTS[k]}
              for k in _REWARD_WEIGHT_KEYS
              if abs(CONFIG[k] - _DEFAULT_REWARD_WEIGHTS[k]) > 1e-9}

st.subheader("Diagnostico")
alertas = []
cob_min = min(ag.get_info()["n_estados_visitados"] for ag in iql.agentes.values()) \
            / N_ESTADOS_TOTAL * 100
if cob_min < 25 and treino.get("n_episodios", 0) > 0:
    alertas.append(f"cobertura_baixa: agente menos visitado cobriu {cob_min:.1f}% "
                    "dos 2160 estados.")
if pesos_mod:
    alertas.append(f"pesos_reward_modificados: {len(pesos_mod)} peso(s) diferem do default.")
if eval_m.get("violacoes_pcc_total", 0) > 0:
    alertas.append(f"violacoes_pcc: {eval_m['violacoes_pcc_total']} horas.")
if eval_m.get("violacoes_soc_total_h", 0) > 0:
    alertas.append(f"violacoes_soc: {eval_m['violacoes_soc_total_h']} horas.")

if alertas:
    for a in alertas:
        st.warning(a)
else:
    st.success("Sem alertas — politica esta dentro dos limites configurados.")

if pesos_mod:
    with st.expander("Pesos do reward modificados"):
        st.json(pesos_mod)
