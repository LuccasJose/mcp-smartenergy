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
with st.expander("Políticas, modelos salvos e protocolo de avaliação"):
    st.markdown("""
**IQL** reúne três agentes de Q-learning: armazenamento, consumo e gerenciamento
de carga. Cada um mantém sua Q-table, com estimativas de valor para ações em
estados discretos; o reward cooperativo é compartilhado.

**Política viva** é o conjunto atualmente disponível para treino e intervenção.
**RL padrão** é a referência congelada. O treino do par usa dois aprendizados
independentes, com o mesmo orçamento por política. O rótulo **RL + LLM MCP**
não significa que o juiz já interveio; essa intervenção é uma etapa distinta.

**Run** armazena uma política e seu histórico. **Modelo salvo**, neste fluxo,
é um experimento com o par de políticas. Carregar não é retreinar: restaura
o artefato e exige nova avaliação para medir o comportamento na base ativa.
Mesmo formato compatível não garante que o modelo pertença à mesma fazenda ou
ao mesmo protocolo. Arquivos de Q-tables devem ser de origem confiável.

**Episódios** são dias simulados repetidos, não novos dados. O orçamento de
500 episódios é apenas um valor inicial da interface, sem garantia de convergência.
Custos durante exploração e custos de avaliação greedy são grandezas diferentes.

**Avaliação legada:** os dias da base ativa também podem ter sido usados no
treino. Esse fluxo não cria uma separação independente de validação e teste;
o protocolo formal pertence aos experimentos de **Divisões do dataset**.
A comparação usa a quantidade solicitada desde o início da base, não um sorteio
representativo do ano. O seletor desta página está limitado a 31 dias.

**SoC propagado** preserva a energia restante entre dias de avaliação. Sem
propagação, cada dia começa da condição inicial, o que muda o problema e pode
mudar os resultados. Comparações exigem a mesma convenção para todas as estratégias.
""")

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
    help="Identificador do run para restaurar a política viva. Vazio usa o run padrão/mais recente. "
         "Não seleciona uma nova fazenda e não demonstra desempenho na base atual.",
)
if col_btn.button("Carregar run", disabled=not st.session_state.mcp_conectado,
                   help="Substitui a política viva por Q-tables salvas. Não executa treinamento; "
                        "a avaliação precisa ser refeita na base ativa."):
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
    "Duas políticas independentes, com o mesmo orçamento por política: RL padrão e RL + LLM MCP. "
    "A quantidade de episódios não garante convergência nem economia."
)

col_a, col_b = st.columns([2, 1])
n_eps = col_a.number_input(
    "Número de episódios",
    min_value=50,
    max_value=1_000_000,
    value=500,
    step=50,
        help="Um episódio simula 24 horas para os três agentes. O valor é aplicado a cada política: "
            "500 significa 1.000 episódios ao todo para o par, além das avaliações de checkpoint.",
)
col_b.metric("Estado atual", "Concluído" if status["treinado"] else "Pendente")

if st.button(
    "Treinar RL padrão + MCP",
    type="primary" if status["proxima_etapa"] == "treinar" else "secondary",
    disabled=not st.session_state.mcp_conectado,
        help="Inicia dois treinamentos e invalida avaliações anteriores. Não executa o LLM-juiz "
            "e não usa as divisões selecionadas na página de experimentos.",
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
               use_container_width=True,
               help="Persiste o par RL padrão/política viva e seus metadados no servidor. "
                   "Não refaz a avaliação nem cria uma separação de teste."):
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
                          list(_rotulo.keys()),
                          help="Experimentos persistidos do par de políticas. Valores de custo são do "
                              "contexto salvo; não são uma nova medição na fazenda atual.")
    _sel = _rotulo[escolha]

    col_ld, col_rn1, col_rn2 = st.columns([1, 2, 1])
    if col_ld.button("Carregar modelo", type="primary",
                     disabled=not st.session_state.mcp_conectado,
                     use_container_width=True,
                     help="Restaura o par de políticas. Confira os avisos de compatibilidade e a origem "
                         "antes de comparar; a base ativa não é substituída pelo nome do modelo."):
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
                                    label_visibility="collapsed",
                                    help="Novo rótulo do experimento. Não muda seu identificador, Q-tables ou resultados.")
    if col_rn2.button("Renomear", disabled=not label_edit.strip(),
                      use_container_width=True,
                      help="Altera somente o rótulo persistido do experimento selecionado."):
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
        help="Quantidade solicitada desde o início da base, sem sorteio ou holdout automático. "
            "Este controle vai até 31 dias; não representa por si só uma avaliação anual.",
    disabled=not st.session_state.treinado,
)
propagar_soc = col_a.checkbox(
    "Manter a bateria entre os dias",
    value=True,
        help="Ligado: o SoC final de um dia inicia o seguinte. Desligado: cada dia recomeça "
            "da condição inicial. As duas opções representam protocolos diferentes.",
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
    if st.button("Carregar RL padrão", disabled=not st.session_state.mcp_conectado,
                  help="Substitui a referência congelada por um run externo. A política viva é preservada; "
                       "use somente arquivos confiáveis e confirme a compatibilidade da fazenda e da física."):
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
        help="Simula as estratégias na base ativa sem treino ou chamadas ao LLM. "
            "Atualiza os históricos usados nos diagnósticos, mas não constitui um teste independente por si só.",
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
    if st.button("Gerar arquivo de exportação", disabled=not status["treinado"],
                  help="Reúne os resultados disponíveis no servidor, sem retreinar. "
                       "O JSON é um relatório; não substitui o salvamento das Q-tables."):
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
              help="Baixa o relatório já gerado. Após novo treino ou comparação, gere outro relatório "
                  "para evitar exportar números de uma execução anterior.",
        )
        st.caption(f"Arquivo gerado em {payload.get('gerado_em', '?')} (UTC).")
