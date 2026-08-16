"""Dashboard Streamlit — SmartEnergy IQL.

Rode com:
    streamlit run src/smarty_energy/mcp/dashboard/app.py

Pré-requisito: o servidor MCP precisa estar rodando à parte:
    python server.py

O dashboard é um CLIENTE MCP puro — toda métrica, log ou ação de
treino/avaliação passa por uma ferramenta do servidor (`state.py` +
`mcp_client.py`). Nenhum dado é calculado localmente.
Cada página (Visão geral, Curva de aprendizado, Trace diário) consome o
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

from smarty_energy.mcp.dashboard.state import MCPServerError, ensure_state, conectar_mcp
from smarty_energy.mcp.dashboard.mcp_client import MCP_SERVER_URL

st.set_page_config(
    page_title="SmartEnergy IQL — Dashboard",
    page_icon="\u26a1",
    layout="wide",
)

ensure_state()

# ── Sidebar: conexão MCP + controles ────────────────────────────────────────

st.sidebar.title("SmartEnergy IQL")
st.sidebar.caption("Painel de gestão e diagnóstico energético")
st.sidebar.info(
    "Use **Executar análise** para preparar os resultados. Depois, abra "
    "**Investigar resultados** para entender o que aconteceu."
)

st.sidebar.divider()

st.sidebar.subheader("Conexão")
if st.sidebar.button("Conectar ao servidor", use_container_width=True,
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
st.sidebar.caption(
    "Fluxo recomendado:\n"
    "1. Executar análise\n"
    "2. Visão geral\n"
    "3. Curva de aprendizado, trace diário ou equipamentos\n"
    "4. Exportar resultados"
)

# ── Conteudo central da home ───────────────────────────────────────────────

st.title("SmartEnergy IQL")
st.caption("Gestão energética por agentes de aprendizado por reforço")

if not st.session_state.mcp_conectado:
    st.header("Comece por aqui")
    st.info(
        "O painel precisa acessar o servidor de dados antes de exibir qualquer resultado. "
        "Clique em **Conectar ao servidor** na barra lateral."
    )
    st.markdown("### Seu fluxo de trabalho")
    st.markdown(
        "1. Abra **Executar análise** no menu lateral.\n"
        "2. Conecte ao servidor e confirme a base carregada.\n"
        "3. Treine, avalie e compare as estratégias.\n"
        "4. Abra **Visão geral** para interpretar o resultado."
    )
else:
    m = st.session_state.meta
    st.header("Resumo da execução")
    st.caption(
        f"Dataset conectado: fazenda {m['id_fazenda']}, de {m['data_inicio']} "
        f"a {m['data_fim']}."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fazenda", m["id_fazenda"])
    c2.metric("Dias no dataset", m["n_dias"])
    c3.metric("Tarifa min (R$/kWh)", f"{m['tarifa_min_rs_kwh']:.4f}")
    c4.metric("Tarifa max (R$/kWh)", f"{m['tarifa_max_rs_kwh']:.4f}")

    st.markdown("### Progresso")
    cs1, cs2, cs3 = st.columns(3)
    cs1.metric("1. Treino", "Concluído" if st.session_state.treinado else "Pendente")
    cs2.metric("2. Avaliação", "Concluída" if st.session_state.avaliado else "Pendente")
    cs3.metric("3. Comparação", "Concluída" if st.session_state.comparado else "Pendente")

    if not st.session_state.treinado:
        st.warning("Próximo passo: abra **Executar análise** e treine os agentes.")
    elif not st.session_state.avaliado:
        st.warning("Próximo passo: abra **Executar análise** e avalie o desempenho do IQL.")
    elif not st.session_state.comparado:
        st.warning("Próximo passo: volte a **Executar análise** e compare as estratégias.")
    else:
        st.success("Fluxo concluído. Comece pela página **Visão geral** para interpretar os resultados.")

    st.markdown("### Próximas tarefas")
    destinos = st.columns(4)
    destinos[0].markdown("**Visão geral**\n\nO resultado completo em um único lugar: qualidade do treino, custo, violações e comparação.")
    destinos[1].markdown("**Curva de aprendizado**\n\nMostra se o agente aprendeu e se o treino se estabilizou.")
    destinos[2].markdown("**Trace diário**\n\nPermite acompanhar as decisões hora a hora em um dia específico.")
    destinos[3].markdown("**Equipamentos**\n\nExplica quais máquinas consomem energia e como as estratégias diferem.")
