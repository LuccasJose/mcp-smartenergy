"""Página Equipamentos — visão por máquina (lógica de BI) + comparação de estratégias.

Toda a página é construída a partir de chamadas MCP:
- get_equipment_stats  → KPIs por equipamento (kWh, horas ligada, pico, custo)
- get_equipment_hourly → uso médio hora-a-hora por equipamento
Comparação entre estratégias usa as chaves do tracker populadas por
compare_strategies: 'rl_llm_mcp', 'rl_padrao', 'heuristico', 'sem_agente'.
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
    require_setup, get_battery_dispatch_stats, get_equipment_stats,
    get_equipment_hourly, MCPServerError,
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
    "rl_llm_mcp":   "RL + LLM MCP",
    "rl_padrao":    "RL padrão",
    "heuristico":   "Heurísticas",
    "sem_agente":   "Sem agentes",
}
ESTRATEGIA_CORES = {
    "rl_llm_mcp":   "rgb(44,160,44)",
    "rl_padrao":    "rgb(31,119,180)",
    "heuristico":   "rgb(255,127,14)",
    "sem_agente":   "rgb(214,39,40)",
}

ORIGENS = {
    "rl_llm_mcp":   "RL + LLM MCP",
    "rl_padrao":    "RL padrão",
    "heuristico":   "Heurísticas",
    "sem_agente":   "Sem agentes",
}

# ── 1. Impacto por equipamento ────────────────────────────────────────────
st.subheader("Onde está o maior impacto?")
st.caption("Comece pelos equipamentos que mais consomem, mais custam ou mais operam no horário de pico.")

origem = st.selectbox("Origem dos dados",
                       options=list(ORIGENS.keys()),
                       format_func=lambda k: ORIGENS[k],
                       help="Escolha qual resultado da análise será usado neste diagnóstico.")

try:
    stats = get_equipment_stats(origem)
except MCPServerError as e:
    stats = {"aviso": str(e)}

if "aviso" in stats:
    st.info(f"{stats['aviso']} — volte a **Executar análise** para avaliar ou comparar.")
else:
    equipamentos = stats["equipamentos"]
    maior_consumo = max(equipamentos, key=lambda nome: equipamentos[nome]["kwh_total"])
    maior_custo = max(equipamentos, key=lambda nome: equipamentos[nome]["custo_energia_rs"])
    maior_pico = max(equipamentos, key=lambda nome: equipamentos[nome]["pct_kwh_em_pico"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dias analisados", stats["n_dias"])
    c2.metric("Consumo total", f"{stats['consumo_total_kwh']:.0f} kWh")
    c3.metric("Maior consumo", EQUIP_LABELS[maior_consumo],
              f"{equipamentos[maior_consumo]['pct_do_consumo_total']:.1f} % do total")
    c4.metric("Maior custo", EQUIP_LABELS[maior_custo],
              f"R${equipamentos[maior_custo]['custo_energia_rs']:.2f}")

    ranking = pd.DataFrame([
        {
            "Chave": nome,
            "Equipamento": EQUIP_LABELS[nome],
            "Consumo total (kWh)": kpi["kwh_total"],
            "Participação no consumo (%)": kpi["pct_do_consumo_total"],
            "Custo de energia (R$)": kpi["custo_energia_rs"],
            "Uso no pico (%)": kpi["pct_kwh_em_pico"],
        }
        for nome, kpi in equipamentos.items()
    ]).sort_values("Custo de energia (R$)", ascending=False)

    fig_ranking = go.Figure(go.Bar(
        x=ranking["Custo de energia (R$)"],
        y=ranking["Equipamento"],
        orientation="h",
        marker_color=[EQUIP_CORES[nome] for nome in ranking["Chave"]],
        text=[f"R${valor:.2f}" for valor in ranking["Custo de energia (R$)"]],
        textposition="outside",
    ))
    fig_ranking.update_layout(
        title="Ranking de custo por equipamento",
        yaxis=dict(autorange="reversed"),
        xaxis_title="Custo de energia (R$)",
        margin=dict(t=50, b=30),
        height=330,
    )
    st.plotly_chart(fig_ranking, use_container_width=True)

    if equipamentos[maior_pico]["pct_kwh_em_pico"] > 0:
        st.warning(
            f"Atenção ao pico tarifário: {EQUIP_LABELS[maior_pico]} concentra "
            f"{equipamentos[maior_pico]['pct_kwh_em_pico']:.1f} % do seu consumo nesse período."
        )

    with st.expander("Detalhes por equipamento"):
        st.dataframe(ranking.drop(columns="Chave").round(2), use_container_width=True, hide_index=True)

st.divider()

# ── 2. Despacho da bateria ─────────────────────────────────────────────────
st.subheader("Despacho da bateria")
st.caption("Os indicadores separam a descarga efetiva no pico, pedidos bloqueados e o nível de SOC ao longo da janela tarifária.")

try:
    bateria = get_battery_dispatch_stats(origem)
except MCPServerError as e:
    bateria = {"aviso": str(e)}

if "aviso" in bateria:
    st.info(bateria["aviso"])
else:
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Descarga no pico", f"{bateria['descarga_pico_media_dia_kwh']:.2f} kWh/dia")
    b2.metric("Parcela da descarga no pico", f"{bateria['pct_descarga_no_pico']:.1f} %")
    b3.metric("Pedidos efetivados", f"{bateria['taxa_descarga_efetiva_pct']:.1f} %")
    b4.metric("SOC após 20h", f"{bateria['soc_medio_apos_20h_pct']:.1f} %"
              if bateria["soc_medio_apos_20h_pct"] is not None else "indisponível")

    c1, c2, c3 = st.columns(3)
    c1.metric("Carga solar", f"{bateria['carga_solar_ac_kwh']:.2f} kWh")
    c2.metric("Carga pela rede", f"{bateria['carga_rede_ac_kwh']:.2f} kWh")
    c3.metric("Custo da arbitragem", f"R$ {bateria['custo_carga_rede_rs']:.2f}")

    bloqueios = bateria["bloqueios_descarga"]
    niveis = bateria["pedidos_por_nivel"]
    d1, d2 = st.columns(2)
    d1.bar_chart(pd.DataFrame({
        "Pedidos": [niveis["2"] if "2" in niveis else niveis[2],
                     niveis["3"] if "3" in niveis else niveis[3],
                     niveis["4"] if "4" in niveis else niveis[4]],
    }, index=["25%", "50%", "100%"]))
    d2.bar_chart(pd.DataFrame({
        "Bloqueios": [bloqueios["sem_deficit"], bloqueios["soc_minimo"],
                      bloqueios["throughput_esgotado"]],
    }, index=["Sem déficit", "SOC mínimo", "Throughput"]))

st.divider()

# ── 3. Uso hora-a-hora dos equipamentos ────────────────────────────────────
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

    # Piv\u00f4 roda 8h consecutivas TODOS os dias, mas o RL escolhe o horário de
    # início dia a dia (janela solar, tarifa etc.). A média entre os 31 dias
    # mistura esses horários diferentes e "espalha" a barra do pivô por mais
    # de 8 posições no gráfico acima — isso não é o pivô ligando por mais
    # tempo, é um efeito da média. O KPI abaixo (por dia individual) confirma
    # o cumprimento da regra; para ver o bloco de 8h intacto num dia
    # específico, use a página **Trace Diário**.
    horas_pivo_dia = equipamentos["pivo"]["horas_ligada_media_dia"] if "aviso" not in stats else None
    if horas_pivo_dia is not None:
        st.info(
            f"**Pivô: {horas_pivo_dia:.1f} h/dia em média — sempre 8h consecutivas por dia.** "
            "A curva acima mostra a média entre os dias; como o horário de início varia "
            "dia a dia, o pivô aparece 'espalhado' por mais de 8 horas no gráfico, mas em "
            "cada dia individual ele roda exatamente 8h seguidas (confira em **Trace Diário**)."
        )

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
    "Compare o equipamento selecionado entre sem agentes, heurísticas, RL padrão "
    "e RL + LLM MCP. Treine o RL padrão + MCP em Executar análise e compare."
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
