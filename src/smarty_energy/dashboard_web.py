"""Dashboard web (Dash/Plotly) — alternativa interativa ao dashboard tkinter.

Abre em localhost:8050. As 3 abas BI (Explorar Dia, Visão Geral Operacional,
Máquina Detalhada) são interativas via Plotly nativo (hover, zoom, click).
Convive com o `dashboard.py` original — use `python main.py --web`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dash import Dash, dcc, html, Input, Output, State, ctx, no_update
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import runs
from .config import CONFIG, BOMBA_HORAS_ON
from .visualization import (
    _MAQUINAS_DETALHE, _MAQ_KPI,
    _metricas_microgrid,
    _custo_por_maquina, _custos_estrategia,
)


# ──────────────────────────────────────────────────────────────
# Paleta — alinhada com o dashboard tkinter
# ──────────────────────────────────────────────────────────────
_COR_S = "#7f8c8d"
_COR_H = "#e74c3c"
_COR_R = "#27ae60"
_PICO_BAND = dict(type="rect", x0=17.5, x1=20.5, y0=0, y1=1,
                  xref="x", yref="paper",
                  fillcolor="orange", opacity=0.12, line_width=0, layer="below")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _labels_dias(dias: list[pd.DataFrame]) -> list[str]:
    return [d["data"].iloc[0].strftime("%d/%m/%Y") for d in dias]


# ──────────────────────────────────────────────────────────────
# Tab 1 — Explorar Dia
# ──────────────────────────────────────────────────────────────

_MAQ_FILTRO_OPTS = ["Todas", "Pivô", "Bomba Captação", "Sede/Escritório", "Secadora/silo"]

# Mapeamento usado na construção do painel de consumo realizado.
# Cada entrada: (cols_demanda, cols_real, cor). Listas com >1 coluna são somadas.
_MAQ_FILTRO_COLS = {
    "Pivô":            (["pivo_kw"],            ["pivo_kw_consumido"],     "#e74c3c"),
    "Bomba Captação":  (["captacao_kw"],        ["captacao_kw_consumido"], "#3498db"),
    "Sede/Escritório": (["sede_kw"],            ["sede_kw_consumido"],     "#9b59b6"),
    "Secadora/silo":   (["silo_kw", "secador_kw"],
                        ["silo_kw_consumido", "secador_kw_consumido"],     "#d35400"),
}


def _fig_explorar_dia(
    dia_df: pd.DataFrame,
    hist_h: list[dict],
    hist_r: list[dict],
    filtro_maq: str,
) -> go.Figure:
    horas = list(range(24))
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Custo por Hora", "Geração vs Consumo",
                        "Consumo Realizado pelo RL", "Origem da Energia (RL)"),
        vertical_spacing=0.16, horizontal_spacing=0.08,
        specs=[[{"type": "xy"}, {"type": "xy"}],
               [{"type": "xy"}, {"type": "domain"}]],
    )

    # (0,0) Custo por hora — agrupado heur vs RL
    fig.add_trace(go.Bar(name="Heurístico", x=horas,
                         y=[r["custo_r"] for r in hist_h],
                         marker_color=_COR_H, opacity=0.85),
                  row=1, col=1)
    fig.add_trace(go.Bar(name="RL", x=horas,
                         y=[r["custo_r"] for r in hist_r],
                         marker_color=_COR_R, opacity=0.85),
                  row=1, col=1)

    # (0,1) Geração vs Consumo
    fig.add_trace(go.Scatter(x=horas, y=[r["geracao_kw"] for r in hist_r],
                             fill="tozeroy", line=dict(color="gold", width=1),
                             fillcolor="rgba(241,196,15,0.3)",
                             name="Geração"),
                  row=1, col=2)
    fig.add_trace(go.Scatter(x=horas, y=[r["consumo_kw"] for r in hist_h],
                             mode="lines+markers", line=dict(color=_COR_H, dash="dash"),
                             marker=dict(size=6), name="Consumo Heur"),
                  row=1, col=2)
    fig.add_trace(go.Scatter(x=horas, y=[r["consumo_kw"] for r in hist_r],
                             mode="lines+markers", line=dict(color=_COR_R),
                             marker=dict(size=6, symbol="square"), name="Consumo RL"),
                  row=1, col=2)

    # (1,0) Consumo realizado — stacked com filtro
    if filtro_maq == "Todas":
        maqs_iter = list(_MAQ_FILTRO_COLS.items())
    else:
        maqs_iter = [(filtro_maq, _MAQ_FILTRO_COLS[filtro_maq])]

    # Demanda histórica como linha pontilhada cinza
    demanda = np.zeros(24)
    for _, (cols_dem, _, _) in maqs_iter:
        for c in cols_dem:
            if c in dia_df.columns:
                demanda += dia_df[c].to_numpy(dtype=float)
    fig.add_trace(go.Scatter(x=horas, y=demanda, mode="lines",
                             line=dict(color=_COR_S, dash="dot", width=1.5),
                             name="Demanda histórica"),
                  row=2, col=1)

    # Barras empilhadas por máquina
    sede_offset = None
    for label, (_, cols_real, cor) in maqs_iter:
        vals = np.zeros(24)
        for c in cols_real:
            vals += np.array([h.get(c, 0.0) for h in hist_r])
        fig.add_trace(go.Bar(x=horas, y=vals, name=label,
                             marker_color=cor, opacity=0.85),
                      row=2, col=1)
        if label == "Sede/Escritório":
            sede_offset = vals.tolist()

    # Marcador de eco-mode na sede (estrela)
    eco_horas = [h for h, reg in enumerate(hist_r) if reg.get("sede_eco")]
    if eco_horas and sede_offset is not None:
        # Posição y: cima da barra de sede em cada hora — aproximação para empilhamento
        fig.add_trace(go.Scatter(
            x=eco_horas, y=[sede_offset[h] + 0.5 for h in eco_horas],
            mode="markers",
            marker=dict(symbol="star", size=14, color="#16a085",
                        line=dict(color="white", width=1)),
            name="Sede em eco-mode (-20%)"),
            row=2, col=1)

    # (1,1) Donut origem (RL agregado do dia)
    ger = sum(h.get("fonte_geracao_kwh", 0.0) for h in hist_r)
    bat = sum(h.get("fonte_bateria_kwh", 0.0) for h in hist_r)
    rede = sum(h.get("fonte_rede_kwh", 0.0) for h in hist_r)
    fig.add_trace(go.Pie(labels=["Geração", "Bateria", "Rede"],
                         values=[ger, bat, rede],
                         marker_colors=["#f1c40f", "#3498db", "#e74c3c"],
                         hole=0.45, name="Origem"),
                  row=2, col=2)

    # Cálculo de custo total para título
    ch = sum(r["custo_r"] for r in hist_h)
    cr = sum(r["custo_r"] for r in hist_r)
    delt = ((cr - ch) / ch * 100) if ch > 0 else 0.0
    titulo = f"Custo: Heur R${ch:.2f}  →  RL R${cr:.2f}  ({delt:+.1f}%)"

    fig.update_layout(
        barmode="stack",
        height=720,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.10, xanchor="center", x=0.5),
        title_text=titulo,
        title_x=0.5,
        margin=dict(t=60, b=80, l=40, r=20),
    )
    # Custo por hora: agrupado em vez de stacked
    fig.update_traces(selector=dict(name="Heurístico"), offsetgroup="0", row=1, col=1)
    fig.update_traces(selector=dict(name="RL"),         offsetgroup="1", row=1, col=1)

    # Faixa do pico nas 3 sub-figuras XY (pula a pie em row=2,col=2)
    for axref in ("x", "x2", "x3"):
        yref = "y" + axref[1:] + " domain"
        fig.add_shape(type="rect", xref=axref, yref=yref,
                      x0=17.5, x1=20.5, y0=0, y1=1,
                      fillcolor="orange", opacity=0.12,
                      line_width=0, layer="below")

    fig.update_xaxes(title_text="Hora", dtick=2, row=1, col=1)
    fig.update_xaxes(title_text="Hora", dtick=2, row=1, col=2)
    fig.update_xaxes(title_text="Hora", dtick=1, row=2, col=1)
    fig.update_yaxes(title_text="R$",   row=1, col=1)
    fig.update_yaxes(title_text="kW",   row=1, col=2)
    fig.update_yaxes(title_text="kW",   row=2, col=1)
    return fig


# ──────────────────────────────────────────────────────────────
# Tab 2 — Visão Geral Operacional
# ──────────────────────────────────────────────────────────────

def _fig_visao_geral(dias, res_s, res_h, res_r) -> go.Figure:
    cst_s_maq = _custo_por_maquina(res_s)
    cst_h_maq = _custo_por_maquina(res_h)
    cst_r_maq = _custo_por_maquina(res_r)
    cst_s = _custos_estrategia(res_s)
    cst_h = _custos_estrategia(res_h)
    cst_r = _custos_estrategia(res_r)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Custo R$ por máquina × estratégia (s/ bat./solar)",
                        "Métricas de microgrid (SCR/SSR em %, PAR razão)",
                        "Carga total — heatmap dia × hora (RL)", ""),
        vertical_spacing=0.15, horizontal_spacing=0.10,
        specs=[[{"type": "xy"}, {"type": "xy"}],
               [{"type": "heatmap", "colspan": 2}, None]],
    )

    # (0,0) Custo R$ por máquina × estratégia (stacked)
    estr = ["Sem Agente", "Heurístico", "RL"]
    for cols, label, cor in _MAQ_KPI:
        fig.add_trace(go.Bar(name=label, x=estr,
                             y=[cst_s_maq[label], cst_h_maq[label], cst_r_maq[label]],
                             marker_color=cor, opacity=0.85,
                             hovertemplate=f"<b>{label}</b><br>R$ %{{y:,.2f}}<extra></extra>"),
                      row=1, col=1)
    # Marcador "diamante" no nível da fatura real em cada barra
    faturas = [cst_s["custo_fatura_total"], cst_h["custo_fatura_total"],
               cst_r["custo_fatura_total"]]
    stack_tots = [sum(cst_s_maq.values()), sum(cst_h_maq.values()), sum(cst_r_maq.values())]
    fig.add_trace(go.Scatter(
        x=estr, y=faturas, mode="markers+text",
        marker=dict(symbol="diamond", size=18, color="#1b4f72",
                    line=dict(color="white", width=2)),
        text=[f"R${f:,.0f}".replace(",", ".") for f in faturas],
        textposition="middle right",
        textfont=dict(size=10, color="#1b4f72", family="Arial Black"),
        name="Fatura real (após bat./solar)",
        hovertemplate="<b>Fatura real</b><br>R$ %{y:,.2f}<extra></extra>"),
        row=1, col=1)
    # Anotação de topo: custo teórico total
    for i, e in enumerate(estr):
        fig.add_annotation(
            xref="x", yref="y",
            x=e, y=stack_tots[i],
            text=f"Teórico<br>R$ {stack_tots[i]:,.0f}".replace(",", "."),
            showarrow=False, yshift=18, font=dict(size=9, color="#566573"),
        )

    # (0,1) SCR/SSR/PAR
    mg_s = _metricas_microgrid(res_s)
    mg_h = _metricas_microgrid(res_h)
    mg_r = _metricas_microgrid(res_r)
    metricas = ["SCR", "SSR", "PAR"]
    for nome, mg, cor in [("Sem Agente", mg_s, _COR_S),
                          ("Heurístico", mg_h, _COR_H),
                          ("RL",         mg_r, _COR_R)]:
        fig.add_trace(go.Bar(name=nome, x=metricas,
                             y=[mg[m] for m in metricas],
                             text=[f"{mg[m]:.1f}" for m in metricas],
                             textposition="outside",
                             marker_color=cor, opacity=0.85,
                             showlegend=False),
                      row=1, col=2)

    # (1,0) Heatmap consolidado
    matriz = np.zeros((len(res_r), 24))
    for d, hist in enumerate(res_r):
        for h in hist:
            soma = sum(h.get(c, 0.0) for cols, _, _ in _MAQ_KPI for c in cols)
            matriz[d, int(h["hora"])] = soma
    datas_y = [d["data"].iloc[0].strftime("%d/%m") for d in dias]
    fig.add_trace(go.Heatmap(z=matriz, x=list(range(24)), y=datas_y,
                             colorscale="Viridis",
                             colorbar=dict(title="kW", thickness=12)),
                  row=2, col=1)

    fig.update_layout(
        barmode="stack",
        height=820,
        legend=dict(orientation="h", yanchor="bottom", y=-0.06, xanchor="center", x=0.5),
        margin=dict(t=50, b=70, l=40, r=20),
    )
    # Heatmap usa barmode="group" para SCR/SSR/PAR — ajuste manual
    fig.update_traces(selector=dict(type="bar"),
                      offsetgroup=None)  # mantém stack default
    # SCR/SSR painel: agrupado, não stacked
    for i in range(len(fig.data)):
        tr = fig.data[i]
        if tr.type == "bar" and tr.name in ("Sem Agente", "Heurístico", "RL"):
            tr.offsetgroup = tr.name

    fig.update_xaxes(title_text="Hora", dtick=2, row=2, col=1)
    fig.update_yaxes(title_text="Dia", row=2, col=1, autorange="reversed")
    fig.update_yaxes(title_text="R$", row=1, col=1)

    # Tooltip explicativo das métricas no painel SCR/SSR/PAR
    fig.add_annotation(
        xref="x2 domain", yref="y2 domain",
        x=0.98, y=0.98,
        text=("<b>SCR</b> ↑ geração consumida / total<br>"
              "<b>SSR</b> ↑ consumo atendido localmente<br>"
              "<b>PAR</b> ↓ achatamento de pico"),
        showarrow=False, align="right",
        bgcolor="rgba(250,250,250,0.95)",
        bordercolor="#bdc3c7", borderwidth=1,
        font=dict(size=10, family="monospace"),
    )
    return fig


# ──────────────────────────────────────────────────────────────
# Tab 3 — Máquina Detalhada
# ──────────────────────────────────────────────────────────────

def _fig_maquina_detalhada(
    nome_maq: str,
    dias: list[pd.DataFrame],
    res_s, res_h, res_r,
) -> tuple[go.Figure, str]:
    """Retorna a figura plotly + texto de resumo HTML."""
    cols_nom, cols_cons, cor, _cmap = _MAQUINAS_DETALHE[nome_maq]

    def _soma_dia(df, cols):
        v = np.zeros(24)
        for c in cols:
            if c in df.columns:
                v += df[c].to_numpy(dtype=float)
        return v

    def _soma_hist(h, cols):
        return sum(h.get(c, 0.0) for c in cols)

    n_dias = len(dias)
    horas = list(range(24))

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("Demanda nominal (heatmap dia × hora)",
                        "Perfil horário médio por estratégia",
                        "Consumo diário total (kWh)",
                        "Distribuição de kWh diário (boxplot)"),
        vertical_spacing=0.16, horizontal_spacing=0.10,
        specs=[[{"type": "heatmap"}, {"type": "xy"}],
               [{"type": "xy"},      {"type": "xy"}]],
    )

    # (0,0) Heatmap demanda nominal
    matriz = np.array([_soma_dia(d, cols_nom) for d in dias])
    z_title = "kW nominal"
    datas_y = [d["data"].iloc[0].strftime("%d/%m") for d in dias]
    fig.add_trace(go.Heatmap(z=matriz, x=horas, y=datas_y,
                             colorscale="YlOrRd",
                             colorbar=dict(title=z_title, thickness=12, x=0.46)),
                  row=1, col=1)

    # (0,1) Perfil horário médio
    def _perfil(resultados):
        m = np.zeros(24)
        for hist in resultados:
            for h in hist:
                m[h["hora"]] += _soma_hist(h, cols_cons)
        return m / max(len(resultados), 1)

    demanda_media = np.mean([_soma_dia(d, cols_nom) for d in dias], axis=0)
    if demanda_media.sum() > 0:
        fig.add_trace(go.Scatter(x=horas, y=demanda_media, fill="tozeroy",
                                 line=dict(color=cor, width=1),
                                 fillcolor=f"rgba(127,140,141,0.2)",
                                 name="Demanda média"),
                      row=1, col=2)

    fig.add_trace(go.Scatter(x=horas, y=_perfil(res_s), mode="lines",
                             line=dict(color=_COR_S, width=2),
                             name="Sem Agente"),
                  row=1, col=2)
    fig.add_trace(go.Scatter(x=horas, y=_perfil(res_h), mode="lines",
                             line=dict(color=_COR_H, dash="dash", width=2),
                             name="Heurístico"),
                  row=1, col=2)
    fig.add_trace(go.Scatter(x=horas, y=_perfil(res_r), mode="lines",
                             line=dict(color=_COR_R, dash="dashdot", width=2.2),
                             name="RL"),
                  row=1, col=2)

    # (1,0) Consumo diário total — barras agrupadas
    diario_s = np.array([sum(_soma_hist(h, cols_cons) for h in hist) for hist in res_s])
    diario_h = np.array([sum(_soma_hist(h, cols_cons) for h in hist) for hist in res_h])
    diario_r = np.array([sum(_soma_hist(h, cols_cons) for h in hist) for hist in res_r])
    dias_x = np.arange(n_dias)
    fig.add_trace(go.Bar(x=dias_x, y=diario_s, name="S (mensal)",
                         marker_color=_COR_S, opacity=0.85, showlegend=False),
                  row=2, col=1)
    fig.add_trace(go.Bar(x=dias_x, y=diario_h, name="H (mensal)",
                         marker_color=_COR_H, opacity=0.85, showlegend=False),
                  row=2, col=1)
    fig.add_trace(go.Bar(x=dias_x, y=diario_r, name="R (mensal)",
                         marker_color=_COR_R, opacity=0.85, showlegend=False),
                  row=2, col=1)

    # (1,1) Boxplot
    fig.add_trace(go.Box(y=diario_s, name="Sem Agente", marker_color=_COR_S, showlegend=False),
                  row=2, col=2)
    fig.add_trace(go.Box(y=diario_h, name="Heurístico", marker_color=_COR_H, showlegend=False),
                  row=2, col=2)
    fig.add_trace(go.Box(y=diario_r, name="RL",         marker_color=_COR_R, showlegend=False),
                  row=2, col=2)

    fig.update_layout(
        height=750,
        title_text=f"Máquina: {nome_maq}",
        title_x=0.5,
        legend=dict(orientation="h", yanchor="bottom", y=-0.08, xanchor="center", x=0.5),
        margin=dict(t=70, b=70, l=40, r=20),
        barmode="group",
    )
    fig.update_xaxes(title_text="Hora", dtick=2, row=1, col=1)
    fig.update_xaxes(title_text="Hora", dtick=2, row=1, col=2)
    fig.update_xaxes(title_text="Dia",  row=2, col=1)
    fig.update_yaxes(title_text="Dia",  row=1, col=1, autorange="reversed")
    fig.update_yaxes(title_text="kW (média)", row=1, col=2)
    fig.update_yaxes(title_text="kWh", row=2, col=1)
    fig.update_yaxes(title_text="kWh/dia", row=2, col=2)

    # Resumo textual (HTML)
    total_s, total_h, total_r = diario_s.sum(), diario_h.sum(), diario_r.sum()
    pct_pico_r = sum(_soma_hist(h, cols_cons)
                     for hist in res_r for h in hist if 18 <= h["hora"] <= 20)
    pct_pico_r = (pct_pico_r / max(total_r, 1e-9)) * 100

    extra = []
    if nome_maq == "Pivô (irrigação)":
        dias_ativ = sum(1 for hist in res_r
                        if any(_soma_hist(h, cols_cons) > 0 for h in hist))
        horas_inicio = [next((h["hora"] for h in hist
                              if _soma_hist(h, cols_cons) > 0), None)
                        for hist in res_r]
        horas_inicio = [h for h in horas_inicio if h is not None]
        h_med = float(np.mean(horas_inicio)) if horas_inicio else 0.0
        dias_8h = 0
        for hist in res_r:
            on = [_soma_hist(h, cols_cons) > 0 for h in hist]
            streak = max_s = 0
            for v in on:
                streak = streak + 1 if v else 0
                max_s = max(max_s, streak)
            if max_s >= 8:
                dias_8h += 1
        extra = [
            f"Dias ativado: {dias_ativ}/{n_dias}",
            f"Hora início média: {h_med:.1f}h",
            f"Dias com 8h consecutivas: {dias_8h}/{n_dias}",
        ]
    elif nome_maq == "Bomba de Captação":
        horas_esperadas = sum(len(BOMBA_HORAS_ON) for _ in res_r)
        horas_cumpridas = sum(1 for hist in res_r for h in hist
                              if h["hora"] in BOMBA_HORAS_ON
                              and _soma_hist(h, cols_cons) > 0)
        pct = (horas_cumpridas / max(horas_esperadas, 1)) * 100
        extra = [
            f"Schedule cumprido: {pct:.1f}% ({horas_cumpridas}/{horas_esperadas})",
            f"kWh médio/dia: {total_r/max(n_dias,1):.1f}",
            f"kWh em pico (RL): {pct_pico_r:.1f}%  (esperado: 0%)",
        ]
    elif nome_maq == "Secadora/silo":
        meta = CONFIG["secador_meta_kwh"]
        dias_meta = sum(1 for d in diario_r if d >= meta)
        extra = [
            f"Meta diária secador: {meta:.1f} kWh",
            f"Dias atingiram: {dias_meta}/{n_dias}",
            f"kWh médio/dia: {float(np.mean(diario_r)):.1f}",
            f"kWh em pico (RL): {pct_pico_r:.1f}%",
        ]
    else:
        extra = [
            "Carga não controlada pelo agente",
            f"kWh médio/dia (RL): {total_r/max(n_dias,1):.1f}",
        ]

    resumo_html = (
        f"<b>{nome_maq}</b><br>"
        f"Consumo total — Sem Agente: <b>{total_s:.1f}</b>  |  "
        f"Heurístico: <b>{total_h:.1f}</b>  |  RL: <b>{total_r:.1f}</b> kWh<br>"
        f"<i>Restrição operacional:</i><br>"
        + "<br>".join(f"&nbsp;&nbsp;• {ln}" for ln in extra)
    )
    return fig, resumo_html


# ──────────────────────────────────────────────────────────────
# Layout
# ──────────────────────────────────────────────────────────────

def _opcoes_run(runs_disp):
    return [{"label": r["label"], "value": r["run_id"]} for r in runs_disp]


def _layout(dias, runs_disp, run_inicial):
    labels_d = _labels_dias(dias)
    nomes_maq = list(_MAQUINAS_DETALHE.keys())
    opcoes_run = _opcoes_run(runs_disp)

    return html.Div([
        html.Div([
            html.Div([
                html.H2("SmartEnergy MAS — Dashboard BI",
                        style={"margin": "0"}),
                html.Span(id="run-atual-badge",
                          style={"color": "#aed6f1", "fontSize": "0.9em",
                                 "fontWeight": "bold"}),
            ], style={"padding": "10px 20px", "background": "#2c3e50",
                      "color": "white", "display": "flex",
                      "alignItems": "baseline", "gap": "16px"}),
            html.Div([
                html.Span(f"{len(dias)} dias  •  3 estratégias (Sem Agente / Heurístico / RL)",
                          style={"color": "#ecf0f1", "fontSize": "0.9em"}),
                html.Div([
                    html.Label("Run (treino):",
                               style={"color": "#ecf0f1", "fontSize": "0.85em",
                                      "marginRight": "8px"}),
                    dcc.Dropdown(id="dd-run", options=opcoes_run, value=run_inicial,
                                 clearable=False,
                                 style={"width": "360px", "color": "#2c3e50"}),
                ], style={"display": "flex", "alignItems": "center"}),
            ], style={"padding": "6px 20px", "background": "#34495e",
                      "display": "flex", "alignItems": "center",
                      "justifyContent": "space-between"}),
        ]),
        dcc.Tabs(id="tabs", value="t-explorar", children=[
            dcc.Tab(label="Explorar Dia", value="t-explorar"),
            dcc.Tab(label="Visão Geral Operacional", value="t-visao"),
            dcc.Tab(label="Máquina Detalhada", value="t-maquina"),
            dcc.Tab(label="Runs / Comparação", value="t-runs"),
        ]),
        html.Div(id="tab-content", style={"padding": "12px 18px"}),

        # Dados invisíveis para callback referenciar
        dcc.Store(id="store-labels", data=labels_d),
        dcc.Store(id="store-maqs",   data=nomes_maq),
        # Tick incrementado a cada mutação de run (rótulo/favorito/apagar)
        dcc.Store(id="store-runs-tick", data=0),
    ])


def _content_explorar(labels_d):
    return html.Div([
        html.Div([
            html.Label("Dia:", style={"marginRight": "8px"}),
            dcc.Dropdown(id="dd-dia",
                         options=[{"label": l, "value": i} for i, l in enumerate(labels_d)],
                         value=0, clearable=False,
                         style={"width": "180px", "display": "inline-block"}),
            html.Label("Máquina:", style={"marginLeft": "24px", "marginRight": "8px"}),
            dcc.Dropdown(id="dd-maq-filtro",
                         options=[{"label": m, "value": m} for m in _MAQ_FILTRO_OPTS],
                         value="Todas", clearable=False,
                         style={"width": "220px", "display": "inline-block"}),
        ], style={"display": "flex", "alignItems": "center", "padding": "10px 0"}),
        dcc.Loading(dcc.Graph(id="g-explorar")),
    ])


def _content_visao():
    return html.Div([
        dcc.Loading(dcc.Graph(id="g-visao")),
    ])


def _content_maquina(nomes_maq):
    return html.Div([
        html.Div([
            html.Label("Máquina:", style={"marginRight": "8px"}),
            dcc.Dropdown(id="dd-maq",
                         options=[{"label": m, "value": m} for m in nomes_maq],
                         value=nomes_maq[0], clearable=False,
                         style={"width": "260px", "display": "inline-block"}),
        ], style={"padding": "10px 0"}),
        html.Div(id="resumo-maq",
                 style={"padding": "12px", "background": "#f5f5f5",
                        "borderRadius": "6px", "marginBottom": "10px",
                        "fontFamily": "Segoe UI"}),
        dcc.Loading(dcc.Graph(id="g-maquina")),
    ])


# ──────────────────────────────────────────────────────────────
# Aba Runs / Comparação
# ──────────────────────────────────────────────────────────────

_NONE_B = "__none__"
_COR_RUN_A = "#2980b9"
_COR_RUN_B = "#e67e22"
_BTN = {"display": "block", "width": "100%", "marginBottom": "8px",
        "padding": "8px", "cursor": "pointer"}


def _reduzir(serie, alvo: int = 1200):
    """Reduz uma série longa a ~`alvo` pontos por média de blocos (plot leve)."""
    n = len(serie)
    if n == 0:
        return [], []
    if n <= alvo:
        return list(range(1, n + 1)), list(serie)
    bloco = n // alvo
    arr = np.asarray(serie[: bloco * alvo], dtype=float).reshape(-1, bloco).mean(axis=1)
    xs = [(i + 1) * bloco for i in range(len(arr))]
    return xs, arr.tolist()


def _fig_comparacao_curvas(run_a, run_b=None):
    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=("Custo por episódio (R$)",
                                        "Reward por episódio"))

    def _add(rid, cor):
        if not rid:
            return
        try:
            h = runs.ler_historico(rid)
        except FileNotFoundError:
            return
        xc, yc = _reduzir(h.get("custos") or [])
        xr, yr = _reduzir(h.get("rewards") or [])
        fig.add_trace(go.Scatter(x=xc, y=yc, name=rid, legendgroup=rid,
                                 line=dict(color=cor)), row=1, col=1)
        fig.add_trace(go.Scatter(x=xr, y=yr, name=rid, legendgroup=rid,
                                 line=dict(color=cor), showlegend=False), row=1, col=2)

    _add(run_a, _COR_RUN_A)
    _add(run_b, _COR_RUN_B)
    fig.update_layout(height=440, margin=dict(t=50, b=60),
                      legend=dict(orientation="h", y=-0.2),
                      title_text="Curvas de aprendizado — Run A (azul) vs Run B (laranja)")
    fig.update_xaxes(title_text="Episódio")
    return fig


def _card_meta(run_id):
    meta = runs.ler_meta(run_id)

    def linha(rotulo, valor):
        return html.Tr([
            html.Td(rotulo, style={"color": "#7f8c8d", "paddingRight": "14px",
                                   "verticalAlign": "top"}),
            html.Td(valor, style={"fontWeight": "bold"}),
        ])

    n = meta.get("n_episodios")
    n_txt = f"{n:,}".replace(",", ".") if isinstance(n, int) else "—"
    custo = meta.get("custo_final")
    if not isinstance(custo, (int, float)):
        custo = meta.get("best_custo_med")
    custo_txt = f"R$ {custo:.2f}" if isinstance(custo, (int, float)) else "—"
    dur = meta.get("duracao_s")
    dur_txt = f"{dur/60:.1f} min" if isinstance(dur, (int, float)) else "—"
    hp = meta.get("hiperparametros") or {}
    hp_txt = ", ".join(f"{k}={v}" for k, v in hp.items()) or "—"

    return html.Table([
        linha("Run", run_id),
        linha("Criado em", meta.get("criado_em", "—")),
        linha("Episódios", n_txt),
        linha("Custo final", custo_txt),
        linha("Best (episódio)", str(meta.get("best_ep", "—"))),
        linha("Duração", dur_txt),
        linha("Hiperparâmetros", hp_txt),
        linha("Fonte de dados", meta.get("fonte_dados", "—")),
        linha("Favorito", "⭐ sim" if meta.get("favorito") else "não"),
    ], style={"fontFamily": "Segoe UI", "fontSize": "0.92em"})


def _content_runs(runs_disp):
    opcoes = _opcoes_run(runs_disp)
    opcoes_b = [{"label": "— nenhum —", "value": _NONE_B}] + opcoes
    return html.Div([
        html.H3("Comparação de runs"),
        html.Div([
            html.Label("Comparar Run atual (A) com Run B:",
                       style={"marginRight": "8px"}),
            dcc.Dropdown(id="dd-run-b", options=opcoes_b, value=_NONE_B,
                         clearable=False, style={"width": "400px"}),
        ], style={"display": "flex", "alignItems": "center", "padding": "6px 0"}),
        dcc.Loading(dcc.Graph(id="g-comparacao")),

        html.Hr(),
        html.H3("Gestão do run atual (A)"),
        html.Div([
            html.Div(id="painel-meta",
                     style={"flex": "1", "background": "#f5f5f5",
                            "borderRadius": "6px", "padding": "12px"}),
            html.Div([
                html.Label("Rótulo:"),
                dcc.Input(id="in-label", type="text", placeholder="ex. alpha-decay",
                          style={"width": "100%", "marginBottom": "8px"}),
                html.Button("Salvar rótulo", id="btn-label", n_clicks=0, style=_BTN),
                html.Button("⭐ Favoritar / desfavoritar", id="btn-fav",
                            n_clicks=0, style=_BTN),
                html.Button("Fixar como run padrão", id="btn-default",
                            n_clicks=0, style=_BTN),
                html.Button("Apagar run", id="btn-del", n_clicks=0,
                            style={**_BTN, "background": "#c0392b", "color": "white"}),
                html.Div(id="msg-gestao",
                         style={"marginTop": "8px", "color": "#1e8449",
                                "fontWeight": "bold"}),
            ], style={"flex": "1", "paddingLeft": "16px"}),
        ], style={"display": "flex", "gap": "16px"}),

        dcc.ConfirmDialog(
            id="confirm-del",
            message="Apagar este run definitivamente? Esta ação não pode ser desfeita.",
        ),
    ])


# ──────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────

def criar_app(
    dias: list[pd.DataFrame],
    res_s: list[list[dict]],
    res_h: list[list[dict]],
    tarifa,
    run_inicial: str,
    runs_disp: list[dict],
    res_r_inicial: list[list[dict]] | None = None,
) -> Dash:
    app = Dash(__name__, title="SmartEnergy MAS — BI",
               suppress_callback_exceptions=True)
    app.layout = _layout(dias, runs_disp, run_inicial)
    labels_d = _labels_dias(dias)
    nomes_maq = list(_MAQUINAS_DETALHE.keys())

    # Cache run_id → res_r. RES_R é recomputado sob demanda ao trocar de run
    # (RES_S/RES_H independem do run). O run inicial já vem pronto.
    _cache_res_r: dict[str, list] = {}
    if res_r_inicial is not None:
        _cache_res_r[run_inicial] = res_r_inicial

    def _get_res_r(run_id):
        if run_id not in _cache_res_r:
            res_r, _ = runs.resultados_rl(run_id, dias, tarifa)
            _cache_res_r[run_id] = res_r
        return _cache_res_r[run_id]

    @app.callback(Output("tab-content", "children"), Input("tabs", "value"))
    def _render_tab(tab):
        if tab == "t-explorar":
            return _content_explorar(labels_d)
        if tab == "t-visao":
            return _content_visao()
        if tab == "t-maquina":
            return _content_maquina(nomes_maq)
        if tab == "t-runs":
            return _content_runs(runs.listar_runs())
        return html.Div("Aba não encontrada")

    @app.callback(Output("run-atual-badge", "children"), Input("dd-run", "value"))
    def _badge(run_id):
        meta = runs.ler_meta(run_id)
        label = (meta.get("label") or "").strip()
        star = "⭐ " if meta.get("favorito") else ""
        nome = f"{label} · {run_id}" if label else run_id
        return f"▶ {star}{nome}"

    @app.callback(Output("g-explorar", "figure"),
                  Input("dd-dia", "value"),
                  Input("dd-maq-filtro", "value"),
                  Input("dd-run", "value"))
    def _upd_explorar(idx, filtro, run_id):
        res_r = _get_res_r(run_id)
        return _fig_explorar_dia(dias[idx], res_h[idx], res_r[idx], filtro)

    @app.callback(Output("g-visao", "figure"),
                  Input("tabs", "value"),
                  Input("dd-run", "value"))
    def _upd_visao(tab, run_id):
        if tab != "t-visao":
            return go.Figure()
        return _fig_visao_geral(dias, res_s, res_h, _get_res_r(run_id))

    @app.callback(Output("g-maquina", "figure"),
                  Output("resumo-maq", "children"),
                  Input("dd-maq", "value"),
                  Input("dd-run", "value"))
    def _upd_maquina(nome, run_id):
        res_r = _get_res_r(run_id)
        fig, resumo_html = _fig_maquina_detalhada(nome, dias, res_s, res_h, res_r)
        return fig, dcc.Markdown(resumo_html, dangerously_allow_html=True)

    # ── Aba Runs / Comparação ─────────────────────────────────────
    @app.callback(Output("g-comparacao", "figure"),
                  Input("dd-run", "value"),
                  Input("dd-run-b", "value"))
    def _upd_comparacao(run_a, run_b):
        rb = None if run_b in (None, _NONE_B) else run_b
        return _fig_comparacao_curvas(run_a, rb)

    @app.callback(Output("painel-meta", "children"),
                  Output("in-label", "value"),
                  Input("dd-run", "value"),
                  Input("store-runs-tick", "data"))
    def _sync_meta(run_id, _tick):
        meta = runs.ler_meta(run_id)
        return _card_meta(run_id), (meta.get("label") or "")

    @app.callback(Output("dd-run", "options"),
                  Output("dd-run-b", "options"),
                  Input("store-runs-tick", "data"))
    def _refresh_opcoes(_tick):
        op = _opcoes_run(runs.listar_runs())
        op_b = [{"label": "— nenhum —", "value": _NONE_B}] + op
        return op, op_b

    @app.callback(Output("confirm-del", "displayed"),
                  Input("btn-del", "n_clicks"),
                  prevent_initial_call=True)
    def _ask_del(_n):
        return True

    @app.callback(
        Output("store-runs-tick", "data"),
        Output("msg-gestao", "children"),
        Output("dd-run", "value"),
        Input("btn-label", "n_clicks"),
        Input("btn-fav", "n_clicks"),
        Input("btn-default", "n_clicks"),
        Input("confirm-del", "submit_n_clicks"),
        State("dd-run", "value"),
        State("in-label", "value"),
        State("store-runs-tick", "data"),
        prevent_initial_call=True,
    )
    def _mutate(_nl, _nf, _nd, _ndel, run_id, label, tick):
        quem = ctx.triggered_id
        novo_valor = no_update
        if quem == "btn-label":
            runs.definir_label(run_id, label or "")
            msg = "Rótulo salvo."
        elif quem == "btn-fav":
            meta = runs.alternar_favorito(run_id)
            msg = "Adicionado aos favoritos." if meta.get("favorito") \
                else "Removido dos favoritos."
        elif quem == "btn-default":
            runs.definir_latest(run_id)
            msg = "Fixado como run padrão (latest)."
        elif quem == "confirm-del":
            novo = runs.deletar_run(run_id)
            if novo is None:
                msg = "Run apagado. Nenhum run restante."
            else:
                msg = f"Run apagado. Exibindo agora: {novo}."
                novo_valor = novo
        else:
            return no_update, no_update, no_update
        return (tick or 0) + 1, msg, novo_valor

    return app


def abrir_dashboard_web(
    dias, res_s, res_h, tarifa,
    run_inicial: str,
    runs_disp: list[dict],
    res_r_inicial=None,
    porta: int = 8050,
    abrir_browser: bool = True,
) -> None:
    """Inicia o servidor Dash em localhost.

    Args:
        run_inicial   : run_id exibido ao abrir.
        runs_disp     : lista de runs (saída de runs.listar_runs) p/ o seletor.
        res_r_inicial : RES_R já calculado do run inicial (evita recomputar).
        porta         : porta TCP (default 8050).
        abrir_browser : abre o browser automaticamente.
    """
    app = criar_app(dias, res_s, res_h, tarifa, run_inicial, runs_disp, res_r_inicial)
    if abrir_browser:
        import threading
        import webbrowser
        url = f"http://127.0.0.1:{porta}"
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  Dashboard web rodando em http://127.0.0.1:{porta}")
    print("  Pressione Ctrl+C para encerrar.\n")
    app.run(debug=False, port=porta, host="127.0.0.1")
