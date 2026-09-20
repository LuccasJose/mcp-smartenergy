"""Página Trace Diário — navega pelos dias, mostra trace + violações por hora.

Roda 1 dia via `run_episode` (tool MCP) em vez de reimplementar o loop de
simulação no dashboard, e lê violações agregadas via `get_hourly_violations`.
Não há nenhum FazendaEnergyEnv/IQLSystem local aqui.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import (
    require_setup, run_episode, select_day, identify_scenarios,
    describe_schema, get_hourly_violations, MCPServerError,
)

st.title("Trace diário")
st.caption("Investigue um dia específico: o que o agente decidiu em cada hora e quais limites foram atingidos?")
with st.expander("Decisões horárias, aprendizado online e continuidade"):
    st.markdown("""
**Trace** é a trajetória de uma simulação diária: estado, ações solicitadas,
fluxos efetivamente realizados, custo e restrições. Uma ação de descarga não
garante descarga: falta de déficit, limites de SoC ou de throughput podem bloqueá-la.
Um bloqueio pode ser uma proteção física correta, não um erro do agente.

**Decisão aprendida** usa a ação de maior valor na Q-table, sem aprendizado online.
**Exploração**, na política viva, faz escolhas epsilon-greedy **e atualiza as
Q-tables**. Portanto, não é uma avaliação neutra de uma política congelada.
O snapshot RL padrão sempre é greedy e não aprende, independentemente desse modo.

**Continuidade** encadeia o SoC final do último trace da mesma política. Isso
não verifica se as datas são consecutivas: saltar de janeiro para dezembro
também transporta a bateria. Sem encadeamento, o início usa o SoC propagado
do IQL, que pode ser o deixado pelo treino, não obrigatoriamente 50%.

Geração e consumo são potências em kW; energia acumulada é medida em kWh.
O custo total pertence ao dia simulado. Já as violações agregadas por hora
pertencem ao histórico da estratégia selecionada, não necessariamente ao trace
exibido. Um dia extremo é útil para diagnóstico, mas não representa o ano inteiro.
""")

if not require_setup():
    st.stop()

try:
    dataset = st.session_state.meta
    cen = identify_scenarios()
    schema = describe_schema()
except MCPServerError as e:
    st.error(str(e))
    st.stop()

soc_min_pct = schema["parametros_fisicos"]["soc_min_pct"]

# ── Seletor de dia ────────────────────────────────────────────────────────
st.subheader("Escolha o cenário para investigar")
st.caption("Comece por um cenário extremo para diagnóstico rápido ou escolha outro dia do dataset manualmente.")
n_dias = dataset["n_dias"]

opcoes_cenario = {"Escolher outro dia": None}
for nome, dados in cen.items():
    rotulo = nome.replace("_", " ").capitalize()
    opcoes_cenario[f"{rotulo} - {dados['data']}"] = dados["dia_idx"]

cenario_escolhido = st.selectbox(
    "Atalho de cenário",
    options=list(opcoes_cenario),
        help="Aponta para dias de geração solar baixa/alta ou consumo elevado na base. "
            "São exemplos diagnósticos, não amostras aleatórias nem uma divisão de teste.",
)
dia_sugerido = opcoes_cenario[cenario_escolhido]

col_a, col_b, col_c = st.columns([3, 1, 1])
dia_idx = col_a.slider("Dia do dataset", 0, n_dias - 1, dia_sugerido or 0,
                   help="Índice começando em zero na base ativa. A data aparece abaixo. "
                       "Mudar a escolha não executa o episódio, mas seleciona o dia no servidor compartilhado.")
mode_label = col_b.selectbox("Comportamento", ["decisão aprendida", "exploração"],
                        help="Decisão aprendida: greedy, sem aprender. Exploração: escolhas aleatórias "
                            "e aprendizado online que modifica a política viva. O RL padrão congelado ignora esse modo.")
mode = "eval" if mode_label == "decisão aprendida" else "train"

try:
    dia_sel = select_day(dia_idx)
    col_c.metric("Cenário", dia_sel["categoria"])
except MCPServerError as e:
    col_c.error("erro")

# Política a simular: a viva (RL + LLM MCP) ou o RL padrão congelado (sem o juiz).
POLITICAS = {
    "rl_llm_mcp": "RL + LLM MCP (política viva)",
    "rl_padrao":  "RL padrão (sem o juiz)",
}
policy = st.radio(
    "Política simulada", options=list(POLITICAS), format_func=lambda k: POLITICAS[k],
    horizontal=True,
    help="RL padrão usa o snapshot congelado ao treinar com os pesos default "
         "(ou carregado de um run externo). É sempre greedy e tem cadeia de "
         "SOC própria.")
if policy == "rl_padrao":
    st.caption("RL padrão é frozen: ignora o seletor de comportamento (roda sempre "
               "greedy) e não é afetado pelo LLM-juiz.")

st.caption(
    f"Data selecionada: **{dia_sel.get('data', '-') }**. "
    f"Cenário classificado como **{dia_sel.get('categoria', '-')}**."
)

if not st.session_state.treinado:
    st.warning("Modelo não treinado. O agente vai jogar quase aleatório.")

# ── Roda 1 episódio (via tool run_episode) ─────────────────────────────────
st.subheader("Execute a simulação")
st.caption("O trace simula o dia escolhido; ele não substitui a avaliação do dataset completo.")
col_run, col_soc = st.columns([1, 3])
continuar_soc = col_soc.toggle(
    "Continuidade da bateria (SOC do dia anterior)", value=False,
    help="Ligado: usa o SoC do último trace da mesma política, mesmo se a data não for consecutiva. "
         "Desligado ou sem trace anterior: usa o SoC propagado do IQL, normalmente pós-treino.")
if col_run.button("Rodar dia", type="primary",
                   help="Simula 24 horas. No modo exploração da política viva, também atualiza suas Q-tables. "
                        "O histórico do trace anterior é substituído."):
    try:
        with st.spinner("Executando episódio via MCP..."):
            resultado = run_episode(mode=mode, dia_idx=dia_idx,
                                     continuar_soc=continuar_soc, policy=policy)
        st.session_state.trace_dia = {
            "passos": resultado["trace"],
            "reward_total": resultado["reward_total"],
            "custo_total": resultado["custo_total_rs"],
            "soc_inicial": resultado.get("soc_inicial_pct"),
            "soc_final": resultado["soc_final_pct"],
            "dia_idx": dia_idx,
            "mode": mode,
            "policy": policy,
        }
    except MCPServerError as e:
        st.error(str(e))

# ── Mostra trace se existir ───────────────────────────────────────────────
if "trace_dia" in st.session_state and st.session_state.trace_dia:
    td = st.session_state.trace_dia
    if td["dia_idx"] != dia_idx or td["mode"] != mode or td.get("policy", "rl_llm_mcp") != policy:
        st.info("Trace mostrado é de outra simulação — clique em 'Rodar dia' para atualizar.")

    st.caption(f"Política do trace: **{POLITICAS.get(td.get('policy', 'rl_llm_mcp'), td.get('policy'))}**")

    df = pd.DataFrame(td["passos"])

    # O trace vem do MCP em JSON (default=str), então flags booleanas chegam
    # como texto "True"/"False" — recoage para bool antes de usar em máscaras.
    # Checa is_bool_dtype (não "== object"): pandas 2/3 usa dtypes de texto
    # diferentes ("object" ou "str" nativo) conforme a versão instalada.
    for _col in ("em_pico_tarifa", "pcc_violado", "soc_violado", "teto_excedido",
                 "bomba_ligada", "bomba_agendada", "sede_eco", "pivo_em_lock"):
        if _col in df.columns and not pd.api.types.is_bool_dtype(df[_col]):
            df[_col] = df[_col].map(lambda v: str(v).strip().lower() in ("true", "1", "1.0"))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Retorno total", f"{td['reward_total']:.2f}")
    c2.metric("Custo total", f"R${td['custo_total']:.2f}")
    soc_ini = td.get("soc_inicial")
    c3.metric("SOC final", f"{td['soc_final']:.1f} %",
               delta=(f"início {soc_ini:.1f} %" if soc_ini is not None else None),
               delta_color="off")
    c4.metric("Violações PCC", int(df["pcc_violado"].sum()))
    bloqueios_descarga = (
        df["motivo_descarga_bloqueada"].notna().sum()
        if "motivo_descarga_bloqueada" in df else 0
    )
    c5.metric("Descargas bloqueadas", int(bloqueios_descarga))

    # ── Plot triplo: geracao/consumo, SOC, custo ──────────────────────
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                          row_heights=[0.45, 0.30, 0.25],
                          vertical_spacing=0.05,
                          subplot_titles=("Geração vs Consumo (kW)",
                                            "SOC (%)",
                                            "Custo horário (R$)"))

    fig.add_trace(go.Scatter(x=df["hora"], y=df["geracao_kw"], mode="lines+markers",
                               name="Geração", line=dict(color="rgb(255,127,14)")),
                    row=1, col=1)
    fig.add_trace(go.Scatter(x=df["hora"], y=df["consumo_kw"], mode="lines+markers",
                               name="Consumo", line=dict(color="rgb(31,119,180)")),
                    row=1, col=1)
    fig.add_trace(go.Bar(x=df["hora"], y=df["bat_descarga"], name="Bat. descarga",
                          marker_color="rgba(44,160,44,0.7)"), row=1, col=1)
    fig.add_trace(go.Bar(x=df["hora"], y=-df["bat_carga"], name="Bat. carga",
                          marker_color="rgba(214,39,40,0.7)"), row=1, col=1)

    fig.add_trace(go.Scatter(x=df["hora"], y=df["soc"], mode="lines+markers",
                               name="SOC", line=dict(color="rgb(148,103,189)"),
                               fill="tozeroy", fillcolor="rgba(148,103,189,0.15)"),
                    row=2, col=1)
    fig.add_hline(y=soc_min_pct, line_dash="dash", line_color="red",
                    annotation_text="SOC min", row=2, col=1)

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

    # ── Uso dos equipamentos hora-a-hora (dia simulado) ─────────────────
    st.subheader("Uso dos equipamentos hora-a-hora")
    EQUIP_TRACE = {
        "pivo_kw_consumido":     ("Pivô",             "rgb(31,119,180)"),
        "captacao_kw_consumido": ("Captação (bomba)", "rgb(255,127,14)"),
        "secador_kw_consumido":  ("Secador",          "rgb(44,160,44)"),
        "sede_kw_consumido":     ("Sede",             "rgb(148,103,189)"),
        "silo_kw_consumido":     ("Silo",             "rgb(140,86,75)"),
    }
    fig_eq = go.Figure()
    for campo, (rotulo, cor) in EQUIP_TRACE.items():
        if campo in df.columns:
            fig_eq.add_trace(go.Bar(x=df["hora"], y=df[campo],
                                      name=rotulo, marker_color=cor))
    fig_eq.add_trace(go.Scatter(x=df["hora"], y=df["geracao_kw"],
                                  name="Geração", mode="lines+markers",
                                  line=dict(color="rgb(188,189,34)", width=2.5)))
    for h_pico in df.loc[df["em_pico_tarifa"], "hora"]:
        fig_eq.add_vrect(x0=h_pico - 0.5, x1=h_pico + 0.5,
                          fillcolor="rgba(214,39,40,0.08)", line_width=0)
    fig_eq.update_layout(barmode="stack", hovermode="x unified",
                           legend=dict(orientation="h", y=1.12),
                           yaxis_title="kW", height=380,
                           margin=dict(t=30, b=40))
    fig_eq.update_xaxes(title_text="Hora (faixa vermelha = pico tarifário)", dtick=1)
    st.plotly_chart(fig_eq, use_container_width=True)

    with st.expander("Decisões hora a hora"):
        colunas_acoes = ["hora", "comando_bateria", "fluxo_bateria", "a_arm", "a_cons", "a_ger", "tarifa",
                          "pivo_kw_consumido", "captacao_kw_consumido",
                          "secador_kw_consumido", "bat_carga", "bat_descarga",
                          "fracao_descarga_solicitada",
                          "motivo_descarga_bloqueada"]
        df_acoes = df[[c for c in colunas_acoes if c in df]].copy()
        st.dataframe(df_acoes.round(2), use_container_width=True, hide_index=True)

st.divider()

# ── Violacoes agregadas por hora (via tool MCP) ───────────────────────────
st.subheader("Violações ao longo do dia")
st.caption("O mapa de calor agrega a última avaliação ou comparação. Cores mais fortes mostram horários mais críticos.")

opcoes_agente = {
    "rl_llm_mcp": "RL + LLM MCP",
    "rl_padrao": "RL padrão",
    "heuristico": "Heurísticas",
    "sem_agente": "Sem agentes",
}
agente_sel = st.selectbox("Origem dos dados",
                            options=list(opcoes_agente.keys()),
                       format_func=lambda k: opcoes_agente[k],
                       help="Estratégia cujo histórico de avaliação alimenta o mapa de violações. "
                           "Não troca a política usada no trace nem dispara uma nova comparação.")

try:
    hv = get_hourly_violations(agente_sel)
except MCPServerError as e:
    hv = {"aviso": str(e)}

if "aviso" in hv:
    st.info(hv["aviso"])
else:
    horas = sorted(int(h) for h in hv.keys())
    metricas = ["violacoes_soc", "violacoes_pcc", "teto_excedido", "kwh_cortado_total"]
    z = np.array([
        [hv[str(h)][m] if str(h) in hv else hv[h][m] for h in horas]
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

    def _get(h, m):
        return hv[str(h)][m] if str(h) in hv else hv[h][m]

    c1, c2, c3 = st.columns(3)
    tot_soc = sum(_get(h, "violacoes_soc") for h in horas)
    tot_pcc = sum(_get(h, "violacoes_pcc") for h in horas)
    tot_teto = sum(_get(h, "teto_excedido") for h in horas)
    c1.metric("Total viol. SOC", tot_soc)
    c2.metric("Total viol. PCC", tot_pcc)
    c3.metric("Total teto excedido", tot_teto)
