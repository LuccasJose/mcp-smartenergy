"""Selecao explicita de protocolos; toda execucao ocorre no servidor MCP."""

import json
import sys
from pathlib import Path

import streamlit as st

_SRC = Path(__file__).resolve().parents[4]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from smarty_energy.mcp.dashboard.state import (
    MCPServerError, evaluate_split_test, get_split_experiment,
    plan_dataset_splits, require_setup, train_split_experiment,
)


st.title("Divisões do dataset")
with st.expander("Critérios dos protocolos", expanded=True):
    st.markdown("""
**Treinamento** é o conjunto em que os agentes aprendem e atualizam suas Q-tables.
**Validação** orienta a escolha do checkpoint e os ajustes experimentais.
**Teste** fica reservado para a avaliação final, sem participar dessas escolhas.

| Método | Distribuição dos dias | Pergunta e limite |
| --- | --- | --- |
| Cronológica | Treino primeiro, validação depois, teste por último. | O aprendizado no passado funciona no futuro? O teste cobre apenas o período final. |
| Aleatória por dias | Dias inteiros sorteados entre os três conjuntos, mantendo as 24 horas juntas. | Funciona em outros dias do mesmo ano? A semelhança entre dias vizinhos pode favorecer o resultado. |
| Blocos por trimestre | Blocos contíguos sorteados dentro de cada trimestre civil. | Funciona nas diferentes condições do ano? Trimestres não equivalem exatamente às estações climáticas. |
| Janelas progressivas | Vários treinos do zero, com histórico crescente e validações sucessivas. O teste final é comum às janelas. | O resultado depende do tamanho do histórico ou da época de validação? Cada janela acrescenta um treinamento. |
| Blocos mensais fixos | Em cada mês, primeiros dias para treino, seguintes para validação e restantes para teste, com cortes configuráveis. | Funciona em blocos reservados ao longo do ano? Não é uma avaliação estritamente futura; meses curtos têm menos dias de teste. |

**Exemplo com 365 dias e proporções 70%/15%/15%:** a divisão cronológica tem
255 dias de treino, 54 de validação e 56 de teste, por arredondamento; não são
cortes por mês. No progressivo com três janelas, os treinos têm 147, 201 e 255
dias. Os quatro métodos base representam seis treinos; incluir o mensal fixo
acrescenta um, totalizando sete.

**Mensal fixo, cortes 24/27:** treino de 1 a 24, validação de 25 a 27 e teste
de 28 até o último dia de cada mês. Não há sobreposição do dia 24. Em 2025,
isso dá **288/36/41 dias**; fevereiro contribui com apenas um dia de teste.
Em um fevereiro bissexto, são dois dias. Percentuais e seed de divisão não
alteram esses cortes. Cada mês/ano presente deve ter dados nos três conjuntos;
um conjunto vazio causa erro, sem transferir dias de outro mês. Lacunas não
são preenchidas pelo particionamento e a prévia mostra os dias disponíveis.

**Continuidade da bateria:** SoC é o percentual de energia armazenada. Cada
bloco independente começa com 50%; dias consecutivos propagam o SoC final.
Lacunas e o retorno ao início do ciclo reiniciam a bateria em 50%.

**Comparação científica:** um custo menor em outro período não comprova um
protocolo melhor. Os testes dos métodos podem conter dias diferentes, e um dia
de teste de um método pode pertencer ao treino de outro. Não existe um teste
global intocado para escolher, depois, o método de melhor resultado.
""")
if not require_setup():
    st.stop()

ROTULOS = {
    "cronologico": "Cronológica",
    "aleatorio": "Aleatória por dias",
    "sazonal": "Blocos por trimestre",
    "progressivo": "Janelas progressivas",
    "mensal_fixo": "Blocos mensais fixos",
}
metodos = st.multiselect("Métodos", list(ROTULOS), format_func=ROTULOS.get,
                    key="splits_methods",
                    help="Qualquer combinação de 1 a 5 métodos. Nenhum é escolhido automaticamente. "
                        "Cada método exige um treino; o progressivo exige um por janela.")
fonte = st.radio("Fonte", ["Dados ativos", "FEMS anual"], horizontal=True,
              key="splits_source",
              help="Dados ativos usa os dias já carregados no MCP, que podem ser apenas janeiro. "
                  "FEMS anual lê a pasta e o ano informados sem substituir a base ou a política ativa.")
dataset_dir, fazenda, ano = "", "", 0
if fonte == "FEMS anual":
    dataset_dir = st.text_input("Pasta FEMS", value="dados/fems_faz_002",
                               help="Pasta no computador do servidor MCP com os Parquet de consumo, "
                                    "geração e fatura. Não é uma pasta do navegador.")
    col_fazenda, col_ano = st.columns(2)
    fazenda = col_fazenda.text_input("Fazenda", value="FAZ-002",
                                    help="Identificador da fazenda dentro dos arquivos, usado para filtrar os dados.")
    ano = col_ano.number_input("Ano", min_value=2000, max_value=2100, value=2025,
                               help="Ano civil filtrado após a leitura. A prévia mostra os dias realmente disponíveis; "
                                    "escolher um ano não garante que ele esteja completo.")

usa_proporcoes = any(metodo != "mensal_fixo" for metodo in metodos)
col_treino, col_validacao, col_teste = st.columns(3)
treino_pct = col_treino.number_input(
    "Treino (%)", min_value=1, max_value=98, value=70, disabled=not usa_proporcoes,
    help="Fração de aprendizado nos métodos não mensais. No sazonal, aplica-se ao número "
         "de blocos por trimestre. Não altera os cortes mensais fixos.",
)
validacao_pct = col_validacao.number_input(
    "Validação (%)", min_value=1, max_value=98, value=15, disabled=not usa_proporcoes,
    help="Fração para selecionar o checkpoint nos métodos não mensais. Treino e validação "
         "devem reservar uma parcela para teste. Não se aplica ao mensal fixo.",
)
col_teste.metric(
    "Teste (%)", 100 - treino_pct - validacao_pct if usa_proporcoes else "N/A",
    help="Parcela restante dos métodos proporcionais. No mensal fixo, o teste ocupa os dias "
         "após o corte de validação; a proporção real varia conforme o tamanho do mês.",
)

col_corte_treino, col_corte_validacao = st.columns(2)
dia_fim_treino = col_corte_treino.number_input(
    "Mensal: último dia de treino", min_value=1, max_value=29, value=24,
    disabled="mensal_fixo" not in metodos, key="splits_month_train_end",
    help="Corte inclusivo: do dia 1 até este dia, em cada mês/ano. A validação começa "
         "no dia seguinte. Não é quantidade de amostras nem percentual.",
)
dia_fim_validacao = col_corte_validacao.number_input(
    "Mensal: último dia de validação", min_value=2, max_value=30, value=27,
    disabled="mensal_fixo" not in metodos, key="splits_month_validation_end",
    help="Corte inclusivo da validação; o teste começa no dia seguinte e vai ao fim do mês. "
         "Deve ser posterior ao treino e deixar ao menos um dia disponível de teste em cada mês.",
)
if "mensal_fixo" in metodos:
    st.caption(
        f"Mensal: treino 1–{dia_fim_treino}; validação {dia_fim_treino + 1}–{dia_fim_validacao}; "
        f"teste {dia_fim_validacao + 1} até o fim de cada mês."
    )

col_episodios, col_intervalo = st.columns(2)
episodios = col_episodios.number_input("Episódios por treino", min_value=1, max_value=1_000_000,
                                       value=500, step=50, key="splits_episodes",
                                       help="Um episódio simula um dia de 24 horas. Os dias de treino se repetem: "
                                           "500 episódios não significam 500 dias distintos. O orçamento vale por treino.")
intervalo = col_intervalo.number_input("Intervalo de validação (episódios)", min_value=1,
                                       value=100, step=10,
                                       help="Frequência da avaliação usada para escolher o checkpoint. Intervalos "
                                           "menores acrescentam avaliações e tempo de execução. O treino não para antes por isso.")
col_seed_treino, col_seed_divisao = st.columns(2)
seed_treino = col_seed_treino.number_input("Seed de treinamento", min_value=0,
                                          max_value=2**32 - 1, value=42,
                                          help="Controla os sorteios de exploração dos agentes. A mesma seed é reiniciada "
                                              "em cada treino; condições e versões iguais são necessárias para reprodução.")
seed_divisao = col_seed_divisao.number_input("Seed de divisão", min_value=0,
                                                max_value=2**32 - 1, value=42,
                                                help="Controla o sorteio de dias/blocos nos métodos aleatório e sazonal. "
                                                    "É independente da seed de treinamento; não altera os cortes cronológicos ou mensais.")
col_blocos, col_janelas = st.columns(2)
bloco_dias = col_blocos.number_input("Dias por bloco sazonal", min_value=1, max_value=90,
                                      value=7, disabled="sazonal" not in metodos,
                                      help="Tamanho máximo do bloco indivisível em cada trimestre. O bloco começa no "
                                          "primeiro dia disponível, não necessariamente segunda-feira; caudas podem ser menores.")
janelas = col_janelas.number_input("Janelas progressivas", min_value=1, max_value=20,
                                     value=3, disabled="progressivo" not in metodos,
                                     help="Quantidade de treinos independentes com histórico crescente. Mais janelas "
                                         "aumentam o custo e reduzem o primeiro histórico; configurações sem dias suficientes falham.")

pedido = dict(
    metodos=metodos, n_episodios=int(episodios), seed_treino=int(seed_treino),
    seed_divisao=int(seed_divisao), fracao_treino=treino_pct / 100,
    fracao_validacao=validacao_pct / 100, bloco_dias=int(bloco_dias),
    n_janelas=int(janelas), intervalo_avaliacao=int(intervalo),
    dataset_dir=dataset_dir.strip(), id_fazenda=fazenda.strip(), ano=int(ano),
    dia_fim_treino=int(dia_fim_treino), dia_fim_validacao=int(dia_fim_validacao),
)
invalido = (not metodos or (usa_proporcoes and treino_pct + validacao_pct >= 100)
            or ("mensal_fixo" in metodos and dia_fim_treino >= dia_fim_validacao)
            or (fonte == "FEMS anual" and not dataset_dir.strip()))
if st.button("Planejar", icon=":material/table_view:", key="splits_plan", disabled=invalido,
           help="Lê e divide os dados, mas não treina nem avalia. Cria um snapshot do plano "
               "no servidor para que mudanças posteriores não alterem suas entradas."):
    try:
        with st.spinner("Preparando divisões..."):
            previa = plan_dataset_splits(**pedido)
        st.session_state.splits_plan_id = previa["plano_id"]
        st.session_state.splits_request = pedido
    except MCPServerError as erro:
        st.error(str(erro))

if "splits_plan_id" not in st.session_state:
    st.stop()
try:
    plano = get_split_experiment(st.session_state.splits_plan_id)
except MCPServerError as erro:
    st.error(str(erro))
    st.stop()

desatualizado = pedido != st.session_state.splits_request
if desatualizado:
    st.warning("Configuração alterada; prévia desatualizada.")

st.divider()
st.subheader("Plano selecionado")
col_total, col_orcamento, col_soc = st.columns(3)
col_total.metric("Treinamentos IQL", plano["n_treinamentos"],
                  help="Uma política nova por divisão, incluindo cada janela progressiva. Não é o par legado RL + MCP.")
col_orcamento.metric("Episódios totais", plano["n_episodios_total"],
                      help="Soma dos episódios de todos os treinos; não inclui o custo adicional de validação e teste.")
col_soc.metric("SoC inicial por bloco", "50%",
                help="Condição inicial igual para RL, heurístico e sem-agente, sem ligar artificialmente dias descontínuos.")
st.caption(f"{plano['fonte']['id_fazenda']} | {plano['fonte']['n_dias']} dias | "
           f"{plano['fonte']['data_inicio']} a {plano['fonte']['data_fim']}")
st.dataframe([
    {"Divisão": divisao["id"], "Treino (dias)": divisao["treino"]["n_dias"],
     "Validação (dias)": divisao["validacao"]["n_dias"], "Teste (dias)": divisao["teste"]["n_dias"],
     "Blocos de treino": len(divisao["treino"]["blocos"]),
     "Dias sem uso": divisao["dias_nao_utilizados"]}
    for divisao in plano["divisoes"]
], hide_index=True, use_container_width=True)
if len(plano["metodos"]) > 1:
    st.warning("Protocolos diferentes podem avaliar períodos diferentes; custos absolutos não definem o melhor protocolo.")
with st.expander("Períodos e configuração"):
    st.json({nome: valor for nome, valor in plano.items() if nome != "resultados"})

pendentes = [divisao for divisao in plano["divisoes"] if divisao["id"] not in plano["resultados"]]
if st.button("Treinar e validar selecionados", icon=":material/play_arrow:",
           key="splits_train", disabled=desatualizado or not pendentes or plano["teste_aberto"],
           help="Executa apenas as divisões pendentes deste plano, sem abrir o teste nem chamar o LLM. "
               "Salva runs isolados, sem substituir a política ativa ou o run padrão."):
    progresso = st.progress(0)
    try:
        for indice, divisao in enumerate(pendentes, start=1):
            with st.spinner(f"Treinando {divisao['id']}..."):
                train_split_experiment(plano["plano_id"], divisao["id"])
            progresso.progress(indice / len(pendentes))
    except MCPServerError as erro:
        st.error(str(erro))
    plano = get_split_experiment(plano["plano_id"])

st.subheader("Resultados")
aba_validacao, aba_teste = st.tabs(["Validação", "Teste final"])
for aba, conjunto in ((aba_validacao, "validacao"), (aba_teste, "teste")):
    with aba:
        if conjunto == "validacao":
            st.markdown("**Validação:** dados usados para escolher o checkpoint de menor custo médio "
                        "diário. RL e baselines são medidos nos mesmos dias e sob a mesma condição de SoC. "
                        "Esses números orientam ajustes, mas não são uma estimativa final independente.")
        else:
            st.markdown("**Teste final:** dados excluídos do treino e da seleção de checkpoint desta divisão. "
                        "A política fica fixa. Ajustá-la após observar estes números compromete a independência "
                        "do teste; as janelas progressivas compartilham o mesmo teste, não testes independentes.")
        st.caption("R$/dia: custo médio diário; rede kWh/dia: energia média importada; "
                   "violações SoC h/dia: horas médias abaixo do limite mínimo configurado. "
                   "Zero nesta última métrica não comprova todas as restrições físicas.")
        linhas = []
        for identificador, resultado in plano["resultados"].items():
            for estrategia, metricas in (resultado[conjunto] or {}).items():
                linhas.append({"Divisão": identificador, "Estratégia": estrategia,
                               "Dias": metricas["n_dias"], "R$/dia": metricas["custo_medio_dia_rs"],
                               "Rede kWh/dia": metricas["rede_media_dia_kwh"],
                               "Violações SoC h/dia": metricas["violacoes_soc_media_h_dia"]})
        if linhas:
            st.dataframe(linhas, hide_index=True, use_container_width=True)
        else:
            st.caption("Reservado" if conjunto == "teste" else "Pendente")

concluido = len(plano["resultados"]) == plano["n_treinamentos"]
teste_pendente = any(resultado["teste"] is None for resultado in plano["resultados"].values())
confirmado = st.checkbox("Liberar teste final deste plano", key=f"splits_confirm_{plano['plano_id']}",
                    disabled=desatualizado or not concluido or not teste_pendente,
                    help="Confirma a abertura do conjunto reservado após concluir todos os treinos do plano. "
                        "O teste não deve orientar uma nova escolha de hiperparâmetros ou do protocolo.")
if st.button("Avaliar teste final", icon=":material/fact_check:", key="splits_test",
           disabled=desatualizado or not confirmado or not concluido or not teste_pendente,
           help="Avalia as políticas já treinadas, sem exploração ou aprendizado. "
               "Resultados já calculados no mesmo plano são reutilizados."):
    try:
        for divisao in plano["divisoes"]:
            with st.spinner(f"Avaliando teste de {divisao['id']}..."):
                evaluate_split_test(plano["plano_id"], divisao["id"], confirmar=True)
        st.rerun()
    except MCPServerError as erro:
        st.error(str(erro))

st.download_button("Relatório JSON", json.dumps(plano, ensure_ascii=False, indent=2),
                   file_name=f"divisoes_{plano['plano_id']}.json", mime="application/json",
                icon=":material/download:",
                help="Exporta datas, blocos, seeds, configuração, hash da entrada e resultados disponíveis. "
                    "O JSON não contém as Q-tables e não restaura automaticamente o plano após reiniciar o MCP.")