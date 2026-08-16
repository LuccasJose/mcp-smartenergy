"""Página Equipamentos — visão por máquina (lógica de BI) + comparação de estratégias.

Toda a página é construída a partir de chamadas MCP:
- get_equipment_stats  → KPIs por equipamento (kWh, horas ligada, pico, custo)
- get_equipment_hourly → uso médio hora-a-hora por equipamento
Comparação entre estratégias usa as chaves do tracker populadas por
compare_strategies: 'iql_eval_cmp' (RL), 'heuristico', 'sem_agente'.
Nenhum cálculo de métrica acontece no dashboard.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import (
    require_setup, get_equipment_stats, get_equipment_hourly, MCPServerError,
)

st.title("Equipamentos")
st.caption("Descubra quais máquinas concentram o consumo e em quais horários cada estratégia as utiliza.")

if not require_setup():
    st.stop()

EQUIP_LABELS = {
    "pivo": "Pivô",
    "captacao": "Captação (bomba)",
    "secador": "Secador",
    "sede": "Sede",
    "silo": "Silo",
}
EQUIP_CORES = {
    "pivo":     "rgb(31,119,180)",
    "captacao": "rgb(255,127,14)",
    "secador":  "rgb(44,160,44)",
    "sede":     "rgb(148,103,189)",
    "silo":     "rgb(140,86,75)",
}
ESTRATEGIAS = {
    "iql_eval_cmp": "RL + LLM-juiz (política atual)",
    "iql_puro":     "RL puro (snapshot)",
    "heuristico":   "Heurísticas",
    "sem_agente":   "Sem otimização",
}
ESTRATEGIA_CORES = {
    "iql_eval_cmp": "rgb(44,160,44)",
    "iql_puro":     "rgb(31,119,180)",
    "heuristico":   "rgb(255,127,14)",
    "sem_agente":   "rgb(214,39,40)",
}

ORIGENS = {
    "iql_eval":     "RL — política atual (Avaliar)",
    "iql_eval_cmp": "RL + LLM-juiz (Comparar)",
    "iql_puro":     "RL puro — snapshot (Comparar)",
    "heuristico":   "Heurísticas",
    "sem_agente":   "Sem otimização",
}

# ── 1. KPIs estilo BI por equipamento ──────────────────────────────────────
st.subheader("Consumo por equipamento")
st.caption("Comece aqui para identificar os maiores consumidores e o custo associado a cada máquina.")

origem = st.selectbox("Origem dos dados",
                       options=list(ORIGENS.keys()),
                       format_func=lambda k: ORIGENS[k])

try:
    stats = get_equipment_stats(origem)
except MCPServerError as e:
    stats = {"aviso": str(e)}

if "aviso" in stats:
    st.info(f"{stats['aviso']} — volte a **Executar análise** para avaliar ou comparar.")
else:
    c1, c2 = st.columns(2)
    c1.metric("Dias avaliados", stats["n_dias"])
    c2.metric("Consumo total", f"{stats['consumo_total_kwh']:.0f} kWh")

    for nome, kpi in stats["equipamentos"].items():
        with st.container(border=True):
            cols = st.columns(6)
            cols[0].markdown(f"**{EQUIP_LABELS.get(nome, nome)}**")
            cols[0].caption(f"{kpi['pct_do_consumo_total']:.1f} % do consumo")
            cols[1].metric("kWh total", f"{kpi['kwh_total']:.0f}")
            cols[2].metric("kWh/dia", f"{kpi['kwh_medio_dia']:.1f}")
            cols[3].metric("Horas ligada/dia", f"{kpi['horas_ligada_media_dia']:.1f} h")
            cols[4].metric("% kWh em pico", f"{kpi['pct_kwh_em_pico']:.1f} %")
            cols[5].metric("Custo energia", f"R${kpi['custo_energia_rs']:.2f}")

    # Participação no consumo (donut)
    kwhs = {EQUIP_LABELS[n]: k["kwh_total"] for n, k in stats["equipamentos"].items()}
    fig_pie = go.Figure(go.Pie(
        labels=list(kwhs.keys()), values=list(kwhs.values()), hole=0.45,
        marker=dict(colors=[EQUIP_CORES[n] for n in stats["equipamentos"]]),
    ))
    fig_pie.update_layout(title="Participação no consumo total",
                           margin=dict(t=40, b=10), height=350)
    st.plotly_chart(fig_pie, use_container_width=True)

st.divider()

# ── 2. Uso hora-a-hora dos equipamentos ────────────────────────────────────
st.subheader("Perfil de uso ao longo do dia")
st.caption("A média por hora mostra quando as máquinas trabalham e ajuda a localizar concentração no horário de pico.")

try:
    hourly = get_equipment_hourly(origem)
except MCPServerError as e:
    hourly = {"aviso": str(e)}

if "aviso" in hourly:
    st.info(hourly["aviso"])
else:
    horas = sorted(int(h) for h in hourly.keys())

    def _h(h, campo):
        return hourly.get(str(h), hourly.get(h, {})).get(campo, 0.0)

    fig = go.Figure()
    for nome in EQUIP_LABELS:
        fig.add_trace(go.Bar(
            x=horas, y=[_h(h, nome) for h in horas],
            name=EQUIP_LABELS[nome], marker_color=EQUIP_CORES[nome],
        ))
    fig.add_trace(go.Scatter(
        x=horas, y=[_h(h, "geracao_kw") for h in horas],
        name="Geração", mode="lines+markers",
        line=dict(color="rgb(188,189,34)", width=2.5),
    ))
    fig.update_layout(barmode="stack", hovermode="x unified",
                       legend=dict(orientation="h", y=1.12),
                       yaxis_title="kW médio", height=420,
                       margin=dict(t=30, b=40))
    fig.update_xaxes(title_text="Hora do dia", dtick=1)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Bateria e rede (médias por hora)"):
        fig_b = go.Figure()
        fig_b.add_trace(go.Bar(x=horas, y=[_h(h, "bat_descarga") for h in horas],
                                name="Bat. descarga", marker_color="rgba(44,160,44,0.7)"))
        fig_b.add_trace(go.Bar(x=horas, y=[-_h(h, "bat_carga") for h in horas],
                                name="Bat. carga", marker_color="rgba(214,39,40,0.7)"))
        fig_b.add_trace(go.Scatter(x=horas, y=[_h(h, "rede_kwh") for h in horas],
                                     name="Rede", mode="lines+markers",
                                     line=dict(color="rgb(31,119,180)")))
        fig_b.update_layout(barmode="relative", hovermode="x unified",
                             yaxis_title="kWh médio", height=320,
                             margin=dict(t=20, b=40))
        fig_b.update_xaxes(title_text="Hora do dia", dtick=1)
        st.plotly_chart(fig_b, use_container_width=True)

st.divider()

# ── 3. Comparação entre estratégias ────────────────────────────────────────
st.subheader("Comparação entre estratégias")
st.caption(
    "Compare o equipamento selecionado entre sem otimização, heurísticas, RL puro "
    "e RL + LLM-juiz. O RL puro aparece depois de congelar a política em Executar análise."
)

if not st.session_state.comparado:
    st.info("Volte a **Executar análise** e compare as estratégias para preencher este painel.")
    st.stop()

dados_estrategias: dict[str, dict] = {}
for chave in ESTRATEGIAS:
    try:
        h = get_equipment_hourly(chave)
        if "aviso" not in h:
            dados_estrategias[chave] = h
    except MCPServerError:
        pass

if not dados_estrategias:
    st.warning("Nenhuma estratégia com dados — rode **Comparar** novamente.")
    st.stop()

equip_sel = st.selectbox("Equipamento",
                          options=list(EQUIP_LABELS.keys()),
                          format_func=lambda k: EQUIP_LABELS[k])

fig_cmp = go.Figure()
for chave, h in dados_estrategias.items():
    horas = sorted(int(x) for x in h.keys())
    valores = [h.get(str(x), h.get(x, {})).get(equip_sel, 0.0) for x in horas]
    fig_cmp.add_trace(go.Scatter(
        x=horas, y=valores, mode="lines+markers",
        name=ESTRATEGIAS[chave], line=dict(color=ESTRATEGIA_CORES[chave], width=2.5),
    ))
fig_cmp.update_layout(hovermode="x unified",
                       title=f"{EQUIP_LABELS[equip_sel]} — kW médio por hora",
                       legend=dict(orientation="h", y=1.12),
                       yaxis_title="kW médio", height=420,
                       margin=dict(t=60, b=40))
fig_cmp.update_xaxes(title_text="Hora do dia", dtick=1)
st.plotly_chart(fig_cmp, use_container_width=True)

# Tabela-resumo: kWh, % em pico e custo por equipamento em cada estratégia
linhas = []
for chave in dados_estrategias:
    try:
        s = get_equipment_stats(chave)
    except MCPServerError:
        continue
    if "aviso" in s:
        continue
    for nome, kpi in s["equipamentos"].items():
        linhas.append({
            "Estratégia": ESTRATEGIAS[chave],
            "Equipamento": EQUIP_LABELS.get(nome, nome),
            "kWh/dia": kpi["kwh_medio_dia"],
            "% kWh em pico": kpi["pct_kwh_em_pico"],
            "Custo energia (R$)": kpi["custo_energia_rs"],
        })

if linhas:
    df_cmp = pd.DataFrame(linhas)
    st.dataframe(
        df_cmp.pivot(index="Equipamento", columns="Estratégia",
                      values=["kWh/dia", "% kWh em pico", "Custo energia (R$)"])
              .round(2),
        use_container_width=True,
    )
