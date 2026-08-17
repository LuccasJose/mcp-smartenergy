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
    get_analysis_status,
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

if mensagem := st.session_state.pop("analysis_feedback", None):
    st.success(mensagem)

try:
    status = get_analysis_status()
except MCPServerError as e:
    st.error(str(e))
    st.stop()

MENSAGENS_ETAPA = {
    "treinar": ("Próxima ação: treinar os agentes", "Ainda não existe uma política treinada no servidor."),
    "avaliar": ("Próxima ação: avaliar o IQL", "O treino está pronto; agora meça o desempenho da política atual."),
    "comparar": ("Próxima ação: comparar estratégias", "A avaliação está pronta; compare os resultados antes de investigar."),
    "investigar": ("Análise pronta para investigação", "Abra a Visão geral para o resultado executivo e os diagnósticos."),
}
titulo_etapa, descricao_etapa = MENSAGENS_ETAPA[status["proxima_etapa"]]
st.subheader(titulo_etapa)
st.caption(descricao_etapa)
etapas = st.columns(4)
for coluna, rotulo, concluida in zip(
    etapas,
    ("Treino", "Avaliação", "Comparação", "Investigação"),
    (status["treinado"], status["avaliado"], status["comparado"], status["comparado"]),
):
    coluna.metric(rotulo, "Concluída" if concluida else "Pendente")

st.divider()

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
col_b.metric("Estado atual", "Concluído" if status["treinado"] else "Pendente")

if st.button(
    "Treinar agentes",
    type="primary" if status["proxima_etapa"] == "treinar" else "secondary",
    disabled=not st.session_state.mcp_conectado,
):
    try:
        with st.spinner(f"Treinando {n_eps} episódios..."):
            sumario = treinar(int(n_eps))
        st.session_state.analysis_feedback = (
            f"Treino concluído. Custo médio recente: "
            f"R${sumario['custo_medio_ultimos_50_rs']:.2f}/dia."
        )
        st.rerun()
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
col_b.metric("Avaliação", "Concluída" if status["avaliado"] else "Pendente")
col_b.metric("Comparação", "Concluída" if status["comparado"] else "Pendente")

with st.expander("Opção avançada: comparar com RL puro"):
    st.caption(
        "Congela a política atual antes da comparação. Use esta opção apenas quando "
        "quiser medir o ganho adicional do LLM-juiz sobre o RL sem intervenção."
    )
    if status["rl_puro_congelado"]:
        st.success("Snapshot RL puro disponível para a próxima comparação.")
    elif st.button("Congelar política como RL puro", disabled=not status["treinado"],
                   help="Salva a política atual para comparação posterior."):
        try:
            snapshot_policy("iql_puro")
            st.session_state.analysis_feedback = "Política congelada como RL puro. Agora execute a comparação."
            st.rerun()
        except MCPServerError as e:
            st.error(str(e))

col_a, col_b = st.columns(2)
if col_a.button(
    "Avaliar o IQL",
    type="primary" if status["proxima_etapa"] == "avaliar" else "secondary",
    disabled=not status["treinado"],
    use_container_width=True,
):
    try:
        with st.spinner("Avaliando o desempenho..."):
            resultado = avaliar(int(n_dias), propagar_soc)
        st.session_state.analysis_feedback = (
            f"Avaliação concluída. Custo médio: R${resultado['custo_medio_dia_rs']:.2f}/dia."
        )
        st.rerun()
    except MCPServerError as e:
        st.error(str(e))

if col_b.button(
    "Comparar estratégias",
    type="primary" if status["proxima_etapa"] == "comparar" else "secondary",
    disabled=not status["avaliado"],
    use_container_width=True,
):
    try:
        with st.spinner("Comparando estratégias..."):
            comparar(int(n_dias), propagar_soc)
        with st.spinner("Atualizando a avaliação da política atual..."):
            avaliar(int(n_dias), propagar_soc)
        st.session_state.analysis_feedback = (
            "Comparação concluída. Acesse a Visão geral para interpretar o resultado."
        )
        st.rerun()
    except MCPServerError as e:
        st.error(str(e))

if not status["avaliado"]:
    st.caption("A comparação será liberada depois que a avaliação do IQL for concluída.")

st.divider()
st.header("3. Continuar a investigação")
st.caption(
    "Depois de avaliar, abra Visão geral para o resumo. Use Curva de aprendizado, "
    "Trace diário e Equipamentos para investigar causas e detalhes."
)

if not status["avaliado"]:
    st.info("A avaliação ainda está pendente.")
elif not status["comparado"]:
    st.info("A avaliação foi concluída. Execute também a comparação para liberar todos os diagnósticos.")
else:
    st.success("A análise está pronta para investigação.")

st.divider()
with st.expander("Exportar resultados"):
    st.caption("Gera um arquivo JSON com treino, avaliações, violações e indicadores de equipamentos.")
    if st.button("Gerar arquivo de exportação", disabled=not status["treinado"]):
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
