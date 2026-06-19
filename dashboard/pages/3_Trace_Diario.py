"""Pagina Trace Diario — navega pelos 31 dias, mostra trace + violacoes por hora.

Permite rodar 1 dia em greedy ou exploracao, plotar geracao/consumo/SOC
hora-a-hora e ver heatmap de violacoes agregadas.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashboard.state import (
    require_setup, FazendaEnergyEnv,
    identificar_cenarios, classificar_dia, CONFIG,
)

st.title("Trace Diario")
st.caption("Navegue pelos dias do dataset, veja decisoes hora-a-hora e violacoes.")

if not require_setup():
    st.stop()

ss = st.session_state

# ── Seletor de dia ────────────────────────────────────────────────────────
n_dias = len(ss.dias)
cen = identificar_cenarios(ss.dias)

col_a, col_b, col_c = st.columns([3, 1, 1])
dia_idx = col_a.slider("Dia (indice)", 0, n_dias - 1, 0)
mode = col_b.selectbox("Modo", ["greedy", "exploracao"])
col_c.metric("Cenario", classificar_dia(dia_idx, ss.dias))

st.caption(
    f"Dias extremos do dataset — nublado: idx={cen['nublado']}, "
    f"ensolarado: idx={cen['ensolarado']}, alto_consumo: idx={cen['alto_consumo']}"
)

if not ss.treinado:
    st.warning("Modelo nao treinado. O agente vai jogar quase aleatorio.")

# ── Roda 1 episodio ───────────────────────────────────────────────────────
if st.button("Rodar dia", type="primary"):
    env = FazendaEnergyEnv(ss.dias[dia_idx], ss.tarifa_24h, CONFIG)
    est = env.reset(soc_inicial=ss.iql.soc_propagado)
    s = env.discretizar(est)
    explore = mode == "exploracao"

    passos = []
    reward_total = 0.0
    custo_total = 0.0
    for _ in range(24):
        acoes = ss.iql.agir_todos(s, explorando=explore)
        prox, reward, done, info = env.step(*acoes)
        s = env.discretizar(prox)
        passos.append(info)
        reward_total += reward
        custo_total += info["custo_r"]
    ss.trace_dia = {"passos": passos, "reward_total": reward_total,
                     "custo_total": custo_total, "soc_final": env.soc,
                     "dia_idx": dia_idx, "mode": mode}

# ── Mostra trace se existir ───────────────────────────────────────────────
if "trace_dia" in ss and ss.trace_dia:
    td = ss.trace_dia
    if td["dia_idx"] != dia_idx or td["mode"] != mode:
        st.info("Trace mostrado eh de outra simulacao — clique em 'Rodar dia' para atualizar.")

    df = pd.DataFrame(td["passos"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Reward total", f"{td['reward_total']:.2f}")
    c2.metric("Custo total", f"R${td['custo_total']:.2f}")
    c3.metric("SOC final", f"{td['soc_final']:.1f} %")
    c4.metric("Violacoes PCC", int(df["pcc_violado"].sum()))

    # ── Plot triplo: geracao/consumo, SOC, custo ──────────────────────────
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                          row_heights=[0.45, 0.30, 0.25],
                          vertical_spacing=0.05,
                          subplot_titles=("Geracao vs Consumo (kW)",
                                            "SOC (%)",
                                            "Custo horario (R$)"))

    # Geracao/consumo
    fig.add_trace(go.Scatter(x=df["hora"], y=df["geracao_kw"], mode="lines+markers",
                               name="Geracao", line=dict(color="rgb(255,127,14)")),
                    row=1, col=1)
    fig.add_trace(go.Scatter(x=df["hora"], y=df["consumo_kw"], mode="lines+markers",
                               name="Consumo", line=dict(color="rgb(31,119,180)")),
                    row=1, col=1)
    fig.add_trace(go.Bar(x=df["hora"], y=df["bat_descarga"], name="Bat. descarga",
                          marker_color="rgba(44,160,44,0.7)"), row=1, col=1)
    fig.add_trace(go.Bar(x=df["hora"], y=-df["bat_carga"], name="Bat. carga",
                          marker_color="rgba(214,39,40,0.7)"), row=1, col=1)

    # SOC
    fig.add_trace(go.Scatter(x=df["hora"], y=df["soc"], mode="lines+markers",
                               name="SOC", line=dict(color="rgb(148,103,189)"),
                               fill="tozeroy", fillcolor="rgba(148,103,189,0.15)"),
                    row=2, col=1)
    fig.add_hline(y=CONFIG["soc_min_pct"], line_dash="dash", line_color="red",
                    annotation_text="SOC min", row=2, col=1)

    # Custo (sombreia pico)
    fig.add_trace(go.Bar(x=df["hora"], y=df["custo_r"], name="Custo R$",
                          marker_color=["red" if p else "blue"
                                          for p in df["em_pico_tarifa"]]),
                    row=3, col=1)

    fig.update_layout(height=700, hovermode="x unified",
                        margin=dict(t=60, b=40), showlegend=True,
                        legend=dict(orientation="h", y=-0.05))
    fig.update_xaxes(title_text="Hora", row=3, col=1, dtick=1)
    fig.update_yaxes(title_text="kW", row=1, col=1)
    fig.update_yaxes(title_text="%", row=2, col=1, range=[0, 100])
    fig.update_yaxes(title_text="R$", row=3, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # ── Tabela de acoes ───────────────────────────────────────────────────
    with st.expander("Acoes hora-a-hora (a_arm, a_cons, a_ger)"):
        df_acoes = df[["hora", "a_arm", "a_cons", "a_ger", "tarifa",
                         "pivo_kw_consumido", "captacao_kw_consumido",
                         "secador_kw_consumido", "bat_carga", "bat_descarga"]].copy()
        st.dataframe(df_acoes.round(2), use_container_width=True, hide_index=True)

st.divider()

# ── Violacoes agregadas por hora (eval atual) ─────────────────────────────
st.subheader("Violacoes por hora do dia (avaliacao atual)")
st.caption("Heatmap agregando todos os dias da ultima evaluate ou compare.")

opcoes_agente = {
    "iql_eval": "IQL (evaluate_agents)",
    "iql_eval_cmp": "IQL (compare_strategies)",
    "heuristico": "Heuristico",
    "sem_agente": "SemAgente",
}
agente_sel = st.selectbox("Origem dos dados",
                            options=list(opcoes_agente.keys()),
                            format_func=lambda k: opcoes_agente[k])

hv = ss.tracker.get_hourly_violations(agente_sel)
if "aviso" in hv:
    st.info(hv["aviso"])
else:
    horas = sorted(int(h) for h in hv.keys())
    metricas = ["violacoes_soc", "violacoes_pcc", "teto_excedido", "kwh_cortado_total"]
    z = np.array([
        [hv[h][m] for h in horas]
        for m in metricas
    ])
    fig_hm = go.Figure(go.Heatmap(
        z=z, x=horas, y=["SOC<15%", "PCC>limite", "teto excedido", "kWh cortado"],
        colorscale="Reds",
        text=z, texttemplate="%{text:.0f}", hovertemplate="hora=%{x}<br>%{y}=%{z}<extra></extra>",
    ))
    fig_hm.update_layout(margin=dict(t=10, b=40), height=300)
    fig_hm.update_xaxes(title_text="Hora", dtick=1)
    st.plotly_chart(fig_hm, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    tot_soc = sum(hv[h]["violacoes_soc"] for h in hv)
    tot_pcc = sum(hv[h]["violacoes_pcc"] for h in hv)
    tot_teto = sum(hv[h]["teto_excedido"] for h in hv)
    c1.metric("Total viol. SOC", tot_soc)
    c2.metric("Total viol. PCC", tot_pcc)
    c3.metric("Total teto excedido", tot_teto)
