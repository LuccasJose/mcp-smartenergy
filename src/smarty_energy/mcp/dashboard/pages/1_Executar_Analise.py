"""Página de execução guiada do dashboard.

Concentra o fluxo operacional: conectar, treinar, avaliar, comparar e exportar.
"""

import json
import sys
from pathlib import Path

import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import (
    MCPServerError,
    avaliar,
    comparar,
    export_all_data,
    require_setup,
    snapshot_policy,
    treinar,
)

st.title("Executar análise")
st.caption(
    "Prepare os resultados que serão usados nas páginas de investigação. "
    "Siga as etapas na ordem apresentada."
)

if not require_setup():
    st.stop()

st.header("1. Treinar os agentes")
st.caption(
    "O treinamento ensina os agentes a tomar decisões hora a hora. "
    "Para uma primeira execução, 500 episódios costumam ser suficientes; "
    "treinos maiores podem produzir uma política mais estável."
)

col_a, col_b = st.columns([2, 1])
n_eps = col_a.number_input(
    "Número de episódios",
    min_value=50,
    max_value=1_000_000,
    value=500,
    step=50,
    help="Quantidade de episódios usados para treinar os três agentes IQL.",
)
col_b.metric("Estado atual", "Concluído" if st.session_state.treinado else "Pendente")

if st.button("Treinar agentes", type="primary", disabled=not st.session_state.mcp_conectado):
    try:
        with st.spinner(f"Treinando {n_eps} episódios..."):
            sumario = treinar(int(n_eps))
        st.success(
            f"Treino concluído. Custo médio recente: "
            f"R${sumario['custo_medio_ultimos_50_rs']:.2f}/dia."
        )
    except MCPServerError as e:
        st.error(str(e))

st.divider()
st.header("2. Medir o desempenho")
st.caption(
    "A avaliação mede o IQL em vários dias. A comparação mostra o resultado contra "
    "heurísticas, ausência de otimização e, quando congelado, o RL puro."
)

col_a, col_b = st.columns([2, 1])
n_dias = col_a.slider(
    "Dias para analisar",
    min_value=1,
    max_value=31,
    value=10,
    help="Quantidade de dias usados na avaliação e na comparação.",
    disabled=not st.session_state.treinado,
)
propagar_soc = col_a.checkbox(
    "Manter a bateria entre os dias",
    value=True,
    help="Quando ligado, o estado final da bateria de um dia é usado como início do próximo.",
    disabled=not st.session_state.treinado,
)
col_b.metric("Avaliação", "Concluída" if st.session_state.avaliado else "Pendente")
col_b.metric("Comparação", "Concluída" if st.session_state.comparado else "Pendente")

if st.button("Congelar política como RL puro", disabled=not st.session_state.treinado,
             help="Salva a política atual para comparar o RL puro com a política assistida pelo LLM-juiz."):
    try:
        snapshot_policy("iql_puro")
        st.success("Política congelada como RL puro. Agora execute a comparação.")
    except MCPServerError as e:
        st.error(str(e))

col_a, col_b = st.columns(2)
if col_a.button("Avaliar o IQL", disabled=not st.session_state.treinado, use_container_width=True):
    try:
        with st.spinner("Avaliando o desempenho..."):
            resultado = avaliar(int(n_dias), propagar_soc)
        st.success(f"Avaliação concluída. Custo médio: R${resultado['custo_medio_dia_rs']:.2f}/dia.")
    except MCPServerError as e:
        st.error(str(e))

if col_b.button("Comparar estratégias", disabled=not st.session_state.avaliado, use_container_width=True):
    try:
        with st.spinner("Comparando estratégias..."):
            comparar(int(n_dias), propagar_soc)
        with st.spinner("Atualizando a avaliação da política atual..."):
            avaliar(int(n_dias), propagar_soc)
        st.success("Comparação concluída. Acesse a Visão geral para interpretar o resultado.")
    except MCPServerError as e:
        st.error(str(e))

if not st.session_state.avaliado:
    st.caption("A comparação será liberada depois que a avaliação do IQL for concluída.")

st.divider()
st.header("3. Continuar a investigação")
st.caption(
    "Depois de avaliar, abra Visão geral para o resumo. Use Curva de aprendizado, "
    "Trace diário e Equipamentos para investigar causas e detalhes."
)

if not st.session_state.avaliado:
    st.info("A avaliação ainda está pendente.")
elif not st.session_state.comparado:
    st.info("A avaliação foi concluída. Execute também a comparação para liberar todos os diagnósticos.")
else:
    st.success("A análise está pronta para investigação.")

st.divider()
st.header("4. Exportar resultados")
st.caption("Gera um arquivo JSON com treino, avaliações, violações e indicadores de equipamentos.")

if st.button("Gerar arquivo de exportação", disabled=not st.session_state.treinado):
    try:
        with st.spinner("Reunindo resultados..."):
            st.session_state.export_payload = export_all_data()
    except MCPServerError as e:
        st.error(str(e))

if st.session_state.get("export_payload"):
    payload = st.session_state.export_payload
    st.download_button(
        "Baixar resultados em JSON",
        data=json.dumps(payload, indent=2, ensure_ascii=False),
        file_name="smartenergy_export.json",
        mime="application/json",
    )
    st.caption(f"Arquivo gerado em {payload.get('gerado_em', '?')} (UTC).")
