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
with st.expander("Reward, exploração e estabilidade do aprendizado"):
    st.markdown("""
**Episódio** corresponde a um dia simulado, com até 24 decisões horárias. Os
mesmos dias podem ser repetidos muitas vezes; o eixo de episódios não representa
necessariamente datas diferentes.

**Retorno** é a soma do reward do episódio. Valores maiores são preferidos
pelo objetivo configurado, mas incluem penalidades e bônus além do custo de energia.
Após mudar os pesos do reward, os retornos deixam de ser diretamente comparáveis.
**Custo** permanece expresso em reais por dia, sob as condições simuladas.

**Epsilon** controla a probabilidade de explorar uma ação aleatória. Epsilon
baixo indica menos exploração, não maior precisão. As curvas de treino incluem
essas ações exploratórias e podem diferir da avaliação greedy do checkpoint salvo.

**Média móvel** reduz o ruído visual: janelas maiores deixam a tendência mais
suave, mas podem esconder oscilações e atrasar a percepção de mudanças. Não muda
as Q-tables, o aprendizado ou o critério de seleção do checkpoint.

**Erro TD absoluto** mede o tamanho da diferença entre a estimativa atual e o
alvo de atualização. Estabilidade é um diagnóstico local, não prova de ótimo
global, de economia sustentada ou de desempenho em dados de teste.
""")

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
                  help="Número de episódios agregados na curva suavizada. Uma janela de 20 "
                      "atenua oscilações de curto prazo; valores altos podem ocultar mudanças. Não altera o treino.")
mostrar_eps = col_b.toggle("Mostrar exploração", value=True,
                       help="Exibe epsilon, a probabilidade de escolher uma ação aleatória. "
                           "É apenas uma escolha de visualização; não liga nem desliga a exploração do agente.")

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

custos_validos = np.asarray(custos_ma, dtype=float)
custos_validos = custos_validos[np.isfinite(custos_validos)]
rewards_validos = np.asarray(rewards_ma, dtype=float)
rewards_validos = rewards_validos[np.isfinite(rewards_validos)]

if len(custos_validos) >= 2 and len(rewards_validos) >= 2:
    variacao_custo = (custos_validos[-1] - custos_validos[0]) / max(abs(custos_validos[0]), 1e-9) * 100
    variacao_retorno = (rewards_validos[-1] - rewards_validos[0]) / max(abs(rewards_validos[0]), 1e-9) * 100
    st.subheader("Leitura rápida")
    c1, c2, c3 = st.columns(3)
    c1.metric("Custo recente", f"R${custos_validos[-1]:.2f}/dia", f"{variacao_custo:+.1f} % desde o início")
    c2.metric("Retorno recente", f"{rewards_validos[-1]:.2f}", f"{variacao_retorno:+.1f} % desde o início")
    c3.metric("Exploração final", f"{epsilons[-1]:.3f}" if epsilons else "indisponível")
    if variacao_custo < 0 and variacao_retorno > 0:
        st.success("O treino mostra melhora conjunta: o custo caiu enquanto o retorno aumentou.")
    else:
        st.warning("As tendências de custo e retorno ainda não apontam para melhora conjunta. Inspecione o gráfico e o erro TD.")

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
st.caption("O erro TD compara a estimativa com o alvo de atualização do Q-learning. "
           "Valores menores e estáveis sugerem estabilização, mas não comprovam convergência ou generalização.")

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
