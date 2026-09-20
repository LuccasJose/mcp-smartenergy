import copy
import json

import numpy as np
import pandas as pd
import pytest

from smarty_energy import runs
from smarty_energy.data_splits import METODOS
from smarty_energy.split_experiments import PlanoDivisoes


@pytest.fixture
def base_divisoes(dia_fake, tarifa_fake, cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(runs, "_LATEST", tmp_path / "runs" / "latest.txt")
    dias = [dia_fake.assign(data=data) for data in pd.date_range("2025-01-01", periods=28)]
    return dias, tarifa_fake, cfg, {"fonte": "sintetica", "id_fazenda": "FAZ-TEST"}


def test_plano_nao_treina_e_isola_snapshot(base_divisoes, monkeypatch):
    monkeypatch.setattr("smarty_energy.split_experiments.treinar",
                        lambda *args, **kwargs: pytest.fail("Planejar nao pode treinar"))
    plano = PlanoDivisoes(*base_divisoes, METODOS)
    assert plano.resumo()["n_treinamentos"] == 7
    assert plano.resumo()["resultados"] == {}
    assert not runs.RUNS_DIR.exists()
    base_divisoes[0][0].loc[0, "solar_kw"] = 999
    base_divisoes[1][0] = 999
    base_divisoes[2]["soc_inicial_pct"] = 99
    assert plano.dias[0].loc[0, "solar_kw"] != 999
    assert plano.tarifa[0] != 999
    assert plano.cfg["soc_inicial_pct"] == 50


def test_execucao_separa_dados_preserva_rng_e_libera_teste(base_divisoes, monkeypatch):
    from smarty_energy import split_experiments
    original = split_experiments.treinar
    chamadas = []

    def observar(dias, tarifa, agentes, cfg, **kwargs):
        treino = {dia["data"].iloc[0] for dia in dias}
        validacao = {dia["data"].iloc[0] for dia in kwargs["dias_selecao"]}
        assert not treino & validacao
        chamadas.append((treino, validacao))
        return original(dias, tarifa, agentes, cfg, **kwargs)

    monkeypatch.setattr(split_experiments, "treinar", observar)
    plano = PlanoDivisoes(*base_divisoes, ["cronologico", "aleatorio", "mensal_fixo"], n_episodios=2)
    np.random.seed(89)
    estado_rng = np.random.get_state()
    with pytest.raises(ValueError, match="confirmacao"):
        plano.avaliar_teste("cronologico_1")
    with pytest.raises(ValueError, match="todos os treinos"):
        plano.avaliar_teste("cronologico_1", confirmar=True)
    for divisao in plano.divisoes:
        resultado = plano.treinar_divisao(divisao.identificador, log=lambda mensagem: None)
        assert resultado["teste"] is None
        assert resultado["validacao"]["rl"]["n_dias"] == len(divisao.validacao)
        assert plano.treinar_divisao(divisao.identificador) == resultado
        meta = runs.ler_meta(resultado["run_id"])
        assert meta["protocolo_divisao"]["hash_dados"] == plano.hash_dados
        assert meta["protocolo_divisao"]["seed_treino"] == 42
        assert meta["fonte_dados"] == "sintetica"
    assert len(chamadas) == 3
    np.testing.assert_array_equal(np.random.get_state()[1], estado_rng[1])
    assert np.random.get_state()[2:] == estado_rng[2:]
    assert not runs._LATEST.exists()
    politicas = copy.deepcopy(plano.politicas)
    for divisao in plano.divisoes:
        resultado = plano.avaliar_teste(divisao.identificador, confirmar=True)
        assert resultado["teste"]["rl"]["n_dias"] == len(divisao.teste)
        assert plano.avaliar_teste(divisao.identificador, confirmar=True) == resultado
        for nome, agente in plano.politicas[divisao.identificador].items():
            antes = politicas[divisao.identificador][nome]
            assert antes.n_updates == agente.n_updates == 48
            assert antes.epsilon == agente.epsilon
            assert antes.q_table.keys() == agente.q_table.keys()
            for estado in antes.q_table:
                np.testing.assert_array_equal(antes.q_table[estado], agente.q_table[estado])
    manifesto = runs.RUNS_DIR.parent / "divisoes" / plano.id / "plano.json"
    assert json.loads(manifesto.read_text(encoding="utf-8"))["teste_aberto"] is True


def test_seed_de_treino_reproduz_politica_independente_da_ordem(base_divisoes):
    primeiro = PlanoDivisoes(*base_divisoes, ["cronologico", "aleatorio"], n_episodios=2)
    segundo = PlanoDivisoes(*base_divisoes, ["aleatorio", "cronologico"], n_episodios=2)
    for plano in (primeiro, segundo):
        for divisao in plano.divisoes:
            plano.treinar_divisao(divisao.identificador, log=lambda mensagem: None)
    for identificador, agentes in primeiro.politicas.items():
        for nome, agente in agentes.items():
            outro = segundo.politicas[identificador][nome]
            assert agente.q_table.keys() == outro.q_table.keys()
            for estado in agente.q_table:
                np.testing.assert_array_equal(agente.q_table[estado], outro.q_table[estado])


def test_falha_restaura_rng_e_nao_publica_resultado(base_divisoes, monkeypatch):
    def falhar(*args, **kwargs):
        np.random.random()
        raise RuntimeError("falha sintetica")

    plano = PlanoDivisoes(*base_divisoes, ["cronologico"])
    monkeypatch.setattr("smarty_energy.split_experiments.treinar", falhar)
    antes = np.random.get_state()
    with pytest.raises(RuntimeError, match="sintetica"):
        plano.treinar_divisao("cronologico_1")
    np.testing.assert_array_equal(antes[1], np.random.get_state()[1])
    assert plano.resultados == {}
    with pytest.raises(ValueError, match="nao pertence"):
        plano.treinar_divisao("sazonal_1")


@pytest.fixture
def servidor_divisoes(base_divisoes, monkeypatch):
    from smarty_energy.mcp import server
    monkeypatch.setattr(server, "_state", None)
    server.initialize(loader=lambda: base_divisoes[:2])
    return server


def test_tools_exigem_escolha_e_nao_substituem_estado(servidor_divisoes):
    servidor = servidor_divisoes
    estado = servidor.get_state()
    politica_ativa = estado.iql
    ambiente_ativo = estado.env
    assert "erro" in json.loads(servidor.plan_dataset_splits([]))
    previa = json.loads(servidor.plan_dataset_splits(["cronologico"], n_episodios=1))
    plano_id = previa["plano_id"]
    assert previa["n_treinamentos"] == 1
    assert json.loads(servidor.get_split_experiment(plano_id)) == previa
    assert "erro" in json.loads(servidor.train_split_experiment(plano_id, "aleatorio_1"))
    resultado = json.loads(servidor.train_split_experiment(plano_id, "cronologico_1"))
    assert resultado["teste"] is None
    assert "erro" in json.loads(servidor.evaluate_split_test(plano_id, "cronologico_1"))
    teste = json.loads(servidor.evaluate_split_test(plano_id, "cronologico_1", confirmar=True))
    assert teste["teste"]["rl"]["n_dias"] == 5
    assert estado.iql is politica_ativa
    assert estado.env is ambiente_ativo
    assert all(agente.n_updates == 0 for agente in politica_ativa.agentes.values())


def test_tools_mensal_persistem_cortes_personalizados(servidor_divisoes):
    servidor = servidor_divisoes
    previa = json.loads(servidor.plan_dataset_splits(
        ["mensal_fixo"], n_episodios=1, dia_fim_treino=20, dia_fim_validacao=26,
    ))
    assert previa["parametros"]["dia_fim_treino"] == 20
    assert previa["parametros"]["dia_fim_validacao"] == 26
    divisao, = previa["divisoes"]
    assert [divisao[nome]["n_dias"] for nome in ("treino", "validacao", "teste")] == [20, 6, 2]
    resultado = json.loads(servidor.train_split_experiment(previa["plano_id"], "mensal_fixo_1"))
    meta = runs.ler_meta(resultado["run_id"])
    assert meta["protocolo_divisao"]["parametros"]["dia_fim_treino"] == 20
    assert meta["protocolo_divisao"]["parametros"]["dia_fim_validacao"] == 26
    assert meta["protocolo_divisao"]["divisao"]["validacao"]["blocos"][0]["inicio"].startswith("2025-01-21")
    resultado_teste = json.loads(servidor.evaluate_split_test(previa["plano_id"], "mensal_fixo_1", confirmar=True))
    assert resultado_teste["teste"]["rl"]["n_dias"] == 2
    invalidos = json.loads(servidor.plan_dataset_splits(["mensal_fixo"], dia_fim_treino=27, dia_fim_validacao=24))
    assert "Cortes mensais" in invalidos["erro"]


def test_planejamento_ano_completo_reutiliza_loader_sem_trocar_base(
    servidor_divisoes, base_divisoes, monkeypatch,
):
    from smarty_energy import data_loader
    chamadas = []

    def carregar(pasta, **kwargs):
        chamadas.append((pasta, kwargs))
        return base_divisoes[:2]

    monkeypatch.setattr(data_loader, "_carregar_fems", carregar)
    estado = servidor_divisoes.get_state()
    dias_ativos = estado.dias
    previa = json.loads(servidor_divisoes.plan_dataset_splits(
        ["cronologico"], dataset_dir="dataset-sintetico", id_fazenda="FAZ-TEST", ano=2025,
    ))
    assert chamadas == [("dataset-sintetico", {"mes": 0, "id_fazenda": "FAZ-TEST"})]
    assert previa["fonte"]["fonte"] == "FEMS (dataset-sintetico)"
    assert estado.dias is dias_ativos


@pytest.mark.parametrize("metodos", [["cronologico", "sazonal"], ["mensal_fixo"], list(METODOS)])
def test_dashboard_escolha_previa_execucao_e_teste(servidor_divisoes, monkeypatch, metodos):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from smarty_energy.mcp.dashboard import state
    chamadas = []

    def chamar(nome, **argumentos):
        chamadas.append(nome)
        resposta = json.loads(getattr(servidor_divisoes, nome)(**argumentos))
        if "erro" in resposta:
            raise state.MCPServerError(resposta["erro"])
        return resposta

    monkeypatch.setattr(state, "call_tool", chamar)
    pagina = Path(state.__file__).parent / "pages" / "8_Divisoes_Dataset.py"
    app = AppTest.from_file(str(pagina), default_timeout=20)
    app.session_state["mcp_conectado"] = True
    app.run()
    assert not app.exception
    assert app.button(key="splits_plan").disabled
    assert any("Critérios dos protocolos" == painel.label for painel in app.expander)
    assert "Qualquer combinação" in app.multiselect(key="splits_methods").help
    assert "Um episódio" in app.number_input(key="splits_episodes").help
    assert chamadas == []
    app.multiselect(key="splits_methods").set_value(metodos).run()
    app.number_input(key="splits_episodes").set_value(1).run()
    app.button(key="splits_plan").click().run()
    assert not app.exception
    textos = " ".join(elemento.value for elemento in app.markdown)
    assert "estimativa final independente" in textos
    assert "compromete a independência" in textos
    assert "train_split_experiment" not in chamadas
    assert app.button(key="splits_test").disabled
    app.button(key="splits_train").click().run()
    assert not app.exception
    n_treinos = len(metodos) + (2 if "progressivo" in metodos else 0)
    assert chamadas.count("train_split_experiment") == n_treinos
    assert "evaluate_split_test" not in chamadas
    app.checkbox[0].check().run()
    app.button(key="splits_test").click().run()
    assert not app.exception
    assert chamadas.count("evaluate_split_test") == n_treinos
    assert app.button(key="splits_train").disabled
    app.multiselect(key="splits_methods").set_value(["aleatorio"]).run()
    assert app.button(key="splits_train").disabled
    assert any("desatualizada" in aviso.value for aviso in app.warning)


def test_dashboard_mensal_cortes_e_previa(servidor_divisoes, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from smarty_energy.mcp.dashboard import state

    def chamar(nome, **argumentos):
        assert nome in ("plan_dataset_splits", "get_split_experiment")
        return json.loads(getattr(servidor_divisoes, nome)(**argumentos))

    monkeypatch.setattr(state, "call_tool", chamar)
    pagina = Path(state.__file__).parent / "pages" / "8_Divisoes_Dataset.py"
    app = AppTest.from_file(str(pagina), default_timeout=20)
    app.session_state["mcp_conectado"] = True
    app.run()
    assert app.number_input(key="splits_month_train_end").disabled
    app.multiselect(key="splits_methods").set_value(["mensal_fixo"]).run()
    assert not app.number_input(key="splits_month_train_end").disabled
    assert all(campo.disabled for campo in app.number_input if campo.label in ("Treino (%)", "Validação (%)"))
    app.number_input(key="splits_month_train_end").set_value(27).run()
    assert app.button(key="splits_plan").disabled
    app.number_input(key="splits_month_train_end").set_value(20).run()
    app.number_input(key="splits_month_validation_end").set_value(26).run()
    app.button(key="splits_plan").click().run()
    assert not app.exception
    previa = json.loads(servidor_divisoes.get_split_experiment(app.session_state["splits_plan_id"]))
    assert previa["parametros"]["dia_fim_treino"] == 20
    assert previa["parametros"]["dia_fim_validacao"] == 26
    assert [previa["divisoes"][0][nome]["n_dias"] for nome in ("treino", "validacao", "teste")] == [20, 6, 2]
    app.number_input(key="splits_month_train_end").set_value(21).run()
    assert app.button(key="splits_train").disabled
    assert any("desatualizada" in aviso.value for aviso in app.warning)
    app.multiselect(key="splits_methods").set_value(["mensal_fixo", "cronologico"]).run()
    assert all(not campo.disabled for campo in app.number_input if campo.label in ("Treino (%)", "Validação (%)"))


@pytest.mark.parametrize("arquivo,trecho", [
    ("../app.py", "estado do MCP é compartilhado"),
    ("1_Executar_Analise.py", "dois aprendizados"),
    ("2_Visao_Geral.py", "não é lucro em reais"),
    ("3_Curva_de_Aprendizado.py", "não prova de ótimo"),
    ("4_Trace_Diario.py", "Q-tables**"),
    ("5_Equipamentos.py", "É um custo bruto"),
    ("6_LLM_Juiz.py", "bloqueios técnicos"),
    ("7_Fazendas_FEMS.py", "Seed FEMS"),
    ("8_Divisoes_Dataset.py", "255 dias de treino"),
])
def test_descricoes_disponiveis_sem_conexao(arquivo, trecho, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from smarty_energy.mcp.dashboard import state

    monkeypatch.setattr(state, "call_tool", lambda *args, **kwargs: pytest.fail("Ajuda nao deve chamar MCP"))
    pagina = Path(state.__file__).parent / "pages" / arquivo
    import ast
    ast.parse(pagina.read_text(encoding="utf-8"))
    app = AppTest.from_file(str(pagina), default_timeout=15).run()
    assert not app.exception
    assert len(app.expander) >= 1
    assert trecho in " ".join(elemento.value for elemento in app.markdown)


@pytest.mark.parametrize("arquivo", [
    "../app.py", "1_Executar_Analise.py", "2_Visao_Geral.py", "3_Curva_de_Aprendizado.py",
    "4_Trace_Diario.py", "5_Equipamentos.py", "6_LLM_Juiz.py", "7_Fazendas_FEMS.py",
])
def test_descricoes_e_controles_conectados_sem_efeitos_externos(
    arquivo, servidor_divisoes, monkeypatch,
):
    import sys
    from pathlib import Path
    from types import ModuleType
    import httpx
    from streamlit.testing.v1 import AppTest
    from smarty_energy.mcp.dashboard import state

    def chamar(nome, **argumentos):
        if nome == "get_learning_curve":
            return {"episodios": [0, 1], "rewards": [-2, -1], "rewards_ma": [-2, -1],
                    "custos": [2, 1], "custos_ma": [2, 1], "epsilons": [1, 0.5]}
        permitidas = {
            "get_analysis_status", "list_experiments", "health_report", "get_dataset_info",
            "get_td_error_series", "identify_scenarios", "describe_schema", "select_day",
            "get_hourly_violations", "get_equipment_stats", "get_battery_dispatch_stats",
            "get_equipment_hourly",
        }
        assert nome in permitidas, f"Chamada inesperada: {nome}"
        return json.loads(getattr(servidor_divisoes, nome)(**argumentos))

    monkeypatch.setattr(state, "call_tool", chamar)
    juiz = ModuleType("smarty_energy.mcp.judge_core")
    juiz.DEFAULT_MAX_STEPS = 4
    juiz.DEFAULT_MODEL = "modelo-sintetico"
    juiz.GOAL_DEFAULT = "Auditoria sintetica"
    juiz.ollama_disponivel = lambda: (True, "Ollama simulado pelo teste")
    juiz.run_judge_sync = lambda *args, **kwargs: pytest.fail("Nao executar juiz")
    monkeypatch.setitem(sys.modules, juiz.__name__, juiz)

    class ClienteFems:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, caminho):
            assert caminho == "/v1/fazendas"
            return httpx.Response(200, json=[{
                "id": "FAZ-TEST", "nome": "Sintetica", "tipo": "Média", "tem_irrigacao": True,
                "id_solar": "SOL-MED", "id_eolica": "EOL-MED", "ano": 2025, "seed": 42,
            }], request=httpx.Request("GET", "http://fems.test/v1/fazendas"))

    monkeypatch.setattr(httpx, "Client", ClienteFems)
    pagina = Path(state.__file__).parent / "pages" / arquivo
    app = AppTest.from_file(str(pagina), default_timeout=20)
    app.session_state["mcp_conectado"] = True
    app.session_state["meta"] = json.loads(servidor_divisoes.get_dataset_info())
    app.session_state["treinado"] = True
    app.session_state["comparado"] = False
    app.run()
    assert not app.exception
    assert len(app.expander) >= 1
    for tipo in ("number_input", "slider", "selectbox", "text_area", "checkbox", "toggle", "radio"):
        for controle in getattr(app, tipo):
            assert controle.help, f"Ajuda ausente em {arquivo}: {controle.label}"


def test_descricao_juiz_permanece_visivel_sem_dependencia(monkeypatch):
    import builtins
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from smarty_energy.mcp.dashboard import state
    importar = builtins.__import__

    def importar_sem_juiz(nome, *args, **kwargs):
        if nome == "smarty_energy.mcp.judge_core":
            raise ModuleNotFoundError("Dependencia opcional ausente", name="openai")
        return importar(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importar_sem_juiz)
    pagina = Path(state.__file__).parent / "pages" / "6_LLM_Juiz.py"
    app = AppTest.from_file(str(pagina), default_timeout=15)
    app.session_state["mcp_conectado"] = True
    app.run()
    assert not app.exception
    assert any("openai" in erro.value for erro in app.error)
    assert any("não cria um modo somente leitura" in texto.value for texto in app.markdown)