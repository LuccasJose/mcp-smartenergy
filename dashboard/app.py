"""Dashboard Streamlit — SmartEnergy IQL.

Rode com:
    streamlit run dashboard/app.py

A sidebar contem os controles de setup/treino/avaliacao.
Cada pagina (Overview, Curva de Aprendizado, Trace Diario) consome o
estado compartilhado em st.session_state.
"""

import streamlit as st

from dashboard.state import (
    ensure_state, setup_dataset, treinar, avaliar, comparar,
)

st.set_page_config(
    page_title="SmartEnergy IQL — Dashboard",
    page_icon="energy",
    layout="wide",
)

ensure_state()

# ── Sidebar: setup + controles ─────────────────────────────────────────────

st.sidebar.title("SmartEnergy IQL")
st.sidebar.caption("Dashboard de inspecao do servidor MCP")

st.sidebar.divider()

st.sidebar.subheader("Setup")
if st.sidebar.button("Carregar dataset", use_container_width=True,
                      type="primary" if not st.session_state.dataset_carregado else "secondary"):
    setup_dataset()
    st.sidebar.success(f"{st.session_state.meta['n_dias']} dias carregados "
                        f"({st.session_state.meta['id_fazenda']})")

if st.session_state.dataset_carregado:
    m = st.session_state.meta
    st.sidebar.caption(f"Fazenda **{m['id_fazenda']}** — "
                        f"{m['n_dias']} dias ({m['data_inicio']} → {m['data_fim']})")

st.sidebar.divider()

# Treino
st.sidebar.subheader("Treino")
n_eps = st.sidebar.slider("n_episodios", 50, 5000, 500, step=50,
                           disabled=not st.session_state.dataset_carregado)
if st.sidebar.button("Treinar IQL", use_container_width=True,
                      disabled=not st.session_state.dataset_carregado):
    with st.spinner(f"Treinando {n_eps} episodios..."):
        sumario = treinar(n_eps)
    st.sidebar.success(
        f"OK — custo_med_50ep = R${sumario['custo_medio_ultimos_50_rs']:.2f}/dia, "
        f"epsilon = {sumario['epsilon_final']:.3f}"
    )

st.sidebar.divider()

# Avaliacao
st.sidebar.subheader("Avaliacao")
n_dias_eval = st.sidebar.slider("n_dias", 1, 31, 10,
                                  disabled=not st.session_state.dataset_carregado)
propagar = st.sidebar.checkbox("Propagar SOC entre dias", value=True,
                                 disabled=not st.session_state.dataset_carregado)
col_a, col_b = st.sidebar.columns(2)
if col_a.button("Avaliar", use_container_width=True,
                  disabled=not st.session_state.treinado):
    with st.spinner("Avaliando..."):
        res = avaliar(n_dias_eval, propagar)
    st.sidebar.success(f"custo = R${res['custo_medio_dia_rs']:.2f}/dia")
if col_b.button("Comparar", use_container_width=True,
                  disabled=not st.session_state.treinado):
    with st.spinner("Comparando IQL vs Heuristico vs SemAgente..."):
        comparar(n_dias_eval, propagar)
    st.sidebar.success("Comparacao concluida")

st.sidebar.divider()
st.sidebar.caption(
    "Use o menu acima para navegar entre paginas:\n"
    "1. Overview — veredito do juiz\n"
    "2. Curva de Aprendizado — convergencia\n"
    "3. Trace Diario — dia a dia + violacoes"
)

# ── Conteudo central da home ───────────────────────────────────────────────

st.title("SmartEnergy IQL — Dashboard")

if not st.session_state.dataset_carregado:
    st.info("Comece carregando o dataset na sidebar. O servidor MCP equivalente "
             "esta em `server.py` e expoe as mesmas operacoes via ferramentas para "
             "um LLM-juiz.")
    st.markdown("### Fluxo recomendado")
    st.markdown(
        "1. **Carregar dataset** (download do Google Sheets, ~1s)\n"
        "2. **Treinar IQL** (~500 episodios = ~10s)\n"
        "3. **Avaliar** ou **Comparar com baselines**\n"
        "4. Navegar pelas paginas para inspecionar resultados"
    )
else:
    m = st.session_state.meta
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fazenda", m["id_fazenda"])
    c2.metric("Dias no dataset", m["n_dias"])
    c3.metric("Tarifa min (R$/kWh)", f"{m['tarifa_min_rs_kwh']:.4f}")
    c4.metric("Tarifa max (R$/kWh)", f"{m['tarifa_max_rs_kwh']:.4f}")

    st.markdown("### Status")
    cs1, cs2, cs3 = st.columns(3)
    cs1.metric("Treinado", "sim" if st.session_state.treinado else "nao")
    cs2.metric("Avaliado", "sim" if st.session_state.avaliado else "nao")
    cs3.metric("Comparado", "sim" if st.session_state.comparado else "nao")

    st.markdown(
        "Use as paginas no menu superior para o detalhe. "
        "Comece por **Overview** apos treinar/avaliar."
    )
