"""Página Curva de Aprendizado — reward/custo/epsilon por episódio.

Toda a página é construída a partir de chamadas MCP:
get_learning_curve (reward/custo/epsilon) + get_td_error_series (1 por
agente) — nenhum dado vem de Q-tables ou tracker locais.
"""

import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import require_setup, get_learning_curve, get_td_error_series, MCPServerError

st.title("Curva de aprendizado")
st.caption("Responde a uma pergunta: o agente está aprendendo uma política melhor ao longo dos episódios?")

if not require_setup():
    st.stop()

if not st.session_state.treinado:
    st.info("Sem treino registrado. Volte a **Executar análise** para treinar os agentes primeiro.")
    st.stop()

# ── Controles ─────────────────────────────────────────────────────────────
st.subheader("Como ler o gráfico")
st.caption("Procure por retorno crescente, custo decrescente e exploração reduzida ao longo do treino.")
col_a, col_b = st.columns([2, 1])
janela = col_a.slider("Tamanho da janela da média móvel", 5, 200, 20, step=5,
                      help="Quantidade de episódios usada para suavizar a curva.")
mostrar_eps = col_b.toggle("Mostrar exploração", value=True,
                            help="Exibe o epsilon, que começa alto e diminui conforme o agente explora menos.")

# ── Dados (via MCP) ─────────────────────────────────────────────────────────
try:
    curva = get_learning_curve(janela_media_movel=janela)
except MCPServerError as e:
    st.error(str(e))
    st.stop()

if not curva:
    st.info("Sem episódios de treino registrados no servidor.")
    st.stop()

x = curva["episodios"]
rewards = curva["rewards"]
rewards_ma = curva["rewards_ma"]
custos = curva["custos"]
custos_ma = curva["custos_ma"]
epsilons = curva.get("epsilons", [])

# ── Plot duplo eixo: reward + custo + (opcional epsilon) ──────────────────
fig = make_subplots(specs=[[{"secondary_y": True}]])

fig.add_trace(go.Scatter(x=x, y=rewards, mode="lines",
                           name="Retorno (bruto)",
                           line=dict(color="rgba(31,119,180,0.25)"),
                           hovertemplate="episódio=%{x}<br>retorno=%{y:.2f}<extra></extra>"))
fig.add_trace(go.Scatter(x=x, y=rewards_ma, mode="lines",
                           name=f"Retorno (média {janela})",
                           line=dict(color="rgb(31,119,180)", width=2.5)))

fig.add_trace(go.Scatter(x=x, y=custos, mode="lines",
                           name="Custo (bruto)",
                           line=dict(color="rgba(214,39,40,0.25)"),
                           hovertemplate="ep=%{x}<br>custo=R$%{y:.2f}<extra></extra>"),
                secondary_y=True)
fig.add_trace(go.Scatter(x=x, y=custos_ma, mode="lines",
                           name=f"Custo (MA-{janela})",
                           line=dict(color="rgb(214,39,40)", width=2.5)),
                secondary_y=True)

if mostrar_eps and epsilons:
    fig.add_trace(go.Scatter(x=list(range(len(epsilons))), y=epsilons,
                               mode="lines", name="epsilon",
                               line=dict(color="rgb(44,160,44)", dash="dot")),
                    secondary_y=False)

fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1),
                    margin=dict(t=40, b=40), height=500)
fig.update_xaxes(title_text="Episódio")
fig.update_yaxes(title_text="Retorno / exploração", secondary_y=False)
fig.update_yaxes(title_text="Custo (R$/dia)", secondary_y=True)
st.plotly_chart(fig, use_container_width=True)

# ── Convergencia: TD-error rolante (via MCP, 1 chamada por agente) ────────
st.subheader("Estabilidade do aprendizado")
st.caption("O erro TD mede a diferença entre a previsão e o resultado observado. Valores menores e estáveis indicam convergência.")

AGENTES = ["armazenamento", "consumo", "gerente"]
cols = st.columns(3)
for col, nome in zip(cols, AGENTES):
    try:
        serie = get_td_error_series(nome)
    except MCPServerError as e:
        col.error(str(e))
        continue
    tds = serie.get("td_errors", [])
    if tds:
        tds_abs = np.abs(tds)
        fig_td = go.Figure()
        fig_td.add_trace(go.Scatter(y=tds_abs, mode="lines",
                                       line=dict(color="rgb(148,103,189)")))
        fig_td.update_layout(title=f"<b>{nome}</b><br><sub>|TD| médio recente: "
                                       f"{float(np.mean(tds_abs[-500:])):.2f}</sub>",
                                margin=dict(t=60, b=20), height=240,
                                showlegend=False)
        fig_td.update_xaxes(title_text="update #")
        fig_td.update_yaxes(title_text="|erro TD|")
        col.plotly_chart(fig_td, use_container_width=True)
    else:
        col.info(f"{nome}: sem erros TD registrados")
