"""Dashboard Streamlit — SmartEnergy IQL.

Rode com:
    streamlit run src/smarty_energy/mcp/dashboard/app.py

Pré-requisito: o servidor MCP precisa estar rodando à parte:
    python server.py

O dashboard é um CLIENTE MCP puro — toda métrica, log ou ação de
treino/avaliação passa por uma ferramenta do servidor (`state.py` +
`mcp_client.py`). Nenhum dado é calculado localmente.
Cada página (Overview, Curva de Aprendizado, Trace Diário) consome o
estado compartilhado em st.session_state, que só guarda o último payload
retornado pelo MCP.
"""

import sys
from pathlib import Path

import streamlit as st

# Streamlit executa este arquivo como script, não como módulo do pacote —
# por isso o caminho de `src/` entra no sys.path na mão.
_SRC = Path(__file__).resolve().parents[3]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import (
    MCPServerError, ensure_state, conectar_mcp, treinar, avaliar, comparar,
)
from smarty_energy.mcp.dashboard.mcp_client import MCP_SERVER_URL

st.set_page_config(
    page_title="SmartEnergy IQL — Dashboard",
    page_icon="energy",
    layout="wide",
)

ensure_state()

# ── Sidebar: conexão MCP + controles ────────────────────────────────────────

st.sidebar.title("SmartEnergy IQL")
st.sidebar.caption(f"Dashboard MCP-cliente — servidor em `{MCP_SERVER_URL}`")

st.sidebar.divider()

st.sidebar.subheader("Servidor MCP")
if st.sidebar.button("Conectar", use_container_width=True,
                      type="primary" if not st.session_state.mcp_conectado else "secondary"):
    try:
        meta = conectar_mcp()
        st.sidebar.success(f"{meta['n_dias']} dias carregados ({meta['id_fazenda']})")
    except MCPServerError as e:
        st.sidebar.error(str(e))

if st.session_state.mcp_conectado:
    m = st.session_state.meta
    st.sidebar.caption(f"Fazenda **{m['id_fazenda']}** — "
                        f"{m['n_dias']} dias ({m['data_inicio']} → {m['data_fim']})")

st.sidebar.divider()

# Treino
st.sidebar.subheader("Treino")
n_eps = st.sidebar.slider("n_episodios", 50, 5000, 500, step=50,
                           disabled=not st.session_state.mcp_conectado)
if st.sidebar.button("Treinar IQL", use_container_width=True,
                      disabled=not st.session_state.mcp_conectado):
    try:
        with st.spinner(f"Treinando {n_eps} episodios via MCP..."):
            sumario = treinar(n_eps)
        st.sidebar.success(
            f"OK — custo_med_50ep = R${sumario['custo_medio_ultimos_50_rs']:.2f}/dia, "
            f"epsilon = {sumario['epsilon_final']:.3f}"
        )
    except MCPServerError as e:
        st.sidebar.error(str(e))

st.sidebar.divider()

# Avaliacao
st.sidebar.subheader("Avaliacao")
n_dias_eval = st.sidebar.slider("n_dias", 1, 31, 10,
                                  disabled=not st.session_state.mcp_conectado)
propagar = st.sidebar.checkbox("Propagar SOC entre dias", value=True,
                                 disabled=not st.session_state.mcp_conectado)
col_a, col_b = st.sidebar.columns(2)
if col_a.button("Avaliar", use_container_width=True,
                  disabled=not st.session_state.treinado):
    try:
        with st.spinner("Avaliando via MCP..."):
            res = avaliar(n_dias_eval, propagar)
        st.sidebar.success(f"custo = R${res['custo_medio_dia_rs']:.2f}/dia")
    except MCPServerError as e:
        st.sidebar.error(str(e))
if col_b.button("Comparar", use_container_width=True,
                  disabled=not st.session_state.treinado):
    try:
        with st.spinner("Comparando IQL vs Heuristico vs SemAgente via MCP..."):
            comparar(n_dias_eval, propagar)
        st.sidebar.success("Comparacao concluida")
    except MCPServerError as e:
        st.sidebar.error(str(e))

st.sidebar.divider()
st.sidebar.caption(
    "Use o menu acima para navegar entre paginas:\n"
    "1. Overview — veredito do juiz\n"
    "2. Curva de Aprendizado — convergencia\n"
    "3. Trace Diario — dia a dia + violacoes"
)

# ── Conteudo central da home ───────────────────────────────────────────────

st.title("SmartEnergy IQL — Dashboard")

if not st.session_state.mcp_conectado:
    st.info(
        "Comece clicando em **Conectar** na sidebar. Se der erro, rode o "
        "servidor MCP em outro terminal: `python server.py` — o dashboard "
        "é um cliente MCP e não funciona sem ele."
    )
    st.markdown("### Fluxo recomendado")
    st.markdown(
        "1. **`python server.py`** em um terminal (fica rodando, expõe MCP via HTTP)\n"
        "2. **Conectar** na sidebar deste dashboard\n"
        "3. **Treinar IQL** (~500 episodios = ~10s)\n"
        "4. **Avaliar** ou **Comparar com baselines**\n"
        "5. Navegar pelas paginas para inspecionar resultados"
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
