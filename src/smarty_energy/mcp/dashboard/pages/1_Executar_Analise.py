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
    carregar_politica_atual,
    carregar_rl_padrao,
    comparar,
    export_all_data,
    get_analysis_status,
    list_experiments,
    load_experiment,
    rename_experiment,
    require_setup,
    save_experiment,
    treinar_rl_e_mcp,
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

st.header("1. Carregar ou treinar os agentes")
st.caption("Carregue um run salvo para investigar a política persistida ou treine uma política nova no servidor.")

col_run, col_btn = st.columns([3, 1])
run_id = col_run.text_input(
    "Run salvo para a política viva",
    value="",
    placeholder="vazio = run mais recente",
    help="Carrega as Q-tables usadas por Trace Diário, avaliação e RL + LLM MCP.",
)
if col_btn.button("Carregar run", disabled=not st.session_state.mcp_conectado):
    try:
        res = carregar_politica_atual(run_id.strip())
        st.session_state.analysis_feedback = (
            f"Política viva carregada: {res.get('origem', '?')}. "
            "Avalie ou compare antes de investigar."
        )
        st.rerun()
    except MCPServerError as e:
        st.error(str(e))

st.divider()
st.header("2. Treinar os agentes")
st.caption(
    "Um clique treina DUAS políticas independentes com o mesmo número de "
    "episódios: o RL padrão e o RL + LLM MCP. "
    "Para uma primeira execução, 500 episódios costumam ser suficientes."
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
    "Treinar RL padrão + MCP",
    type="primary" if status["proxima_etapa"] == "treinar" else "secondary",
    disabled=not st.session_state.mcp_conectado,
):
    try:
        with st.spinner(f"Treinando RL padrão + MCP ({n_eps} episódios cada)..."):
            sumario = treinar_rl_e_mcp(int(n_eps))
        if "erro" in sumario:
            st.error(sumario["erro"])
        else:
            st.session_state.analysis_feedback = (
                f"RL padrão: melhor R${sumario['rl_padrao']['best_custo_med_rs']:.2f}/dia · "
                f"MCP: custo médio recente R${sumario['rl_llm_mcp']['custo_medio_ultimos_50_rs']:.2f}/dia."
            )
            st.rerun()
    except MCPServerError as e:
        st.error(str(e))

st.divider()
st.header("Modelos salvos")
st.caption(
    "Salve o par treinado (RL padrão + RL + LLM MCP) como um modelo e "
    "recarregue-o depois — pula a etapa de treino e vai direto à comparação."
)

col_sv1, col_sv2 = st.columns([3, 1])
label_novo = col_sv1.text_input(
    "Nome do modelo",
    value="",
    placeholder="vazio = usa o nº de episódios (ex.: 50000ep)",
    help="Rótulo amigável do modelo salvo; dá para renomear depois.",
)
if col_sv2.button("Salvar modelo", disabled=not status["treinado"],
                  use_container_width=True):
    try:
        res = save_experiment(label_novo.strip())
        if "erro" in res:
            st.error(res["erro"])
        else:
            st.session_state.analysis_feedback = (
                f"Modelo salvo: {res['label']} ({res['exp_id']})."
            )
            st.rerun()
    except MCPServerError as e:
        st.error(str(e))

try:
    _exps = list_experiments().get("experimentos", [])
except MCPServerError:
    _exps = []

if not _exps:
    st.info("Nenhum modelo salvo ainda. Treine e clique em **Salvar modelo**.")
else:
    _rotulo = {
        f"{m['label']}  ·  {m['exp_id']}"
        + (f"  ·  R${m['custos'].get('rl_llm_mcp', '?')}/dia" if m.get("custos") else "")
        + ("  ·  ⚖️ pesos alterados" if m.get("pesos_alterados") else ""): m
        for m in _exps
    }
    escolha = st.selectbox("Modelos disponíveis (mais recente primeiro)",
                           list(_rotulo.keys()))
    _sel = _rotulo[escolha]

    col_ld, col_rn1, col_rn2 = st.columns([1, 2, 1])
    if col_ld.button("Carregar modelo", type="primary",
                     disabled=not st.session_state.mcp_conectado,
                     use_container_width=True):
        try:
            res = load_experiment(_sel["exp_id"])
            if "erro" in res:
                st.error(res["erro"])
            else:
                avisos = res.get("avisos_fisica") or []
                extra = f" Atenção — física divergente: {'; '.join(avisos)}." if avisos else ""
                st.session_state.analysis_feedback = (
                    f"Modelo '{res['label']}' carregado — treino dispensado. "
                    f"Vá direto a **Medir o desempenho**.{extra}"
                )
                st.rerun()
        except MCPServerError as e:
            st.error(str(e))

    label_edit = col_rn1.text_input("Renomear para", value="",
                                    placeholder="novo nome do modelo",
                                    label_visibility="collapsed")
    if col_rn2.button("Renomear", disabled=not label_edit.strip(),
                      use_container_width=True):
        try:
            res = rename_experiment(_sel["exp_id"], label_edit.strip())
            if "erro" in res:
                st.error(res["erro"])
            else:
                st.session_state.analysis_feedback = (
                    f"Modelo {res['exp_id']} renomeado para '{res['label']}'."
                )
                st.rerun()
        except MCPServerError as e:
            st.error(str(e))

    with st.expander("Detalhes do modelo selecionado"):
        st.json(_sel)

st.divider()
st.header("3. Medir o desempenho")
st.caption(
    "Um só passo avalia e compara as 4 estratégias (Sem agentes, Heurísticas, "
    "RL padrão e RL + LLM MCP) nos mesmos dias."
)

col_a, col_b = st.columns([2, 1])
n_dias = col_a.slider(
    "Dias para analisar",
    min_value=1,
    max_value=31,
    value=10,
    help="Quantidade de dias usados na comparação.",
    disabled=not st.session_state.treinado,
)
propagar_soc = col_a.checkbox(
    "Manter a bateria entre os dias",
    value=True,
    help="Quando ligado, o estado final da bateria de um dia é usado como início do próximo.",
    disabled=not st.session_state.treinado,
)
col_b.metric("Comparação", "Concluída" if status["comparado"] else "Pendente")

with st.expander("Opcional: usar o RL do Smart_Energy como RL padrão"):
    _default_runs = _SRC.parent.parent / "Smart_Energy" / "outputs" / "runs"
    rl_dir = st.text_input(
        "Pasta de runs do Smart_Energy", value=str(_default_runs),
        help="Pega o run mais recente com qtable_*.pkl e o congela como 'RL padrão' "
             "(sobrescreve o RL padrão treinado). Não toca no RL + LLM MCP.",
    )
    if st.button("Carregar RL padrão", disabled=not st.session_state.mcp_conectado):
        try:
            res = carregar_rl_padrao(dir_path=rl_dir.strip())
            if "erro" in res:
                st.error(res["erro"])
            else:
                st.session_state.analysis_feedback = (
                    f"RL padrão carregado ({res.get('origem', '?')}). Refaça a comparação."
                )
                st.rerun()
        except MCPServerError as e:
            st.error(str(e))

if st.button(
    "Avaliar e comparar estratégias",
    type="primary" if status["proxima_etapa"] == "comparar" else "secondary",
    disabled=not status["treinado"],
    use_container_width=True,
):
    try:
        with st.spinner("Avaliando e comparando estratégias..."):
            comparar(int(n_dias), propagar_soc)
        st.session_state.analysis_feedback = (
            "Comparação concluída. Acesse a Visão geral para interpretar o resultado."
        )
        st.rerun()
    except MCPServerError as e:
        st.error(str(e))

if not status["treinado"]:
    st.caption("A comparação será liberada depois que o treino for concluído.")

st.divider()
st.header("4. Continuar a investigação")
st.caption(
    "Depois de avaliar, abra Visão geral para o resumo. Use Curva de aprendizado, "
    "Trace diário e Equipamentos para investigar causas e detalhes."
)

if not status["comparado"]:
    st.info("A comparação ainda está pendente.")
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
