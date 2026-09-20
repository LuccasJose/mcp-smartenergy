"""Tools do servidor MCP (configure_*, compare_strategies, health_report).

O servidor e inicializado explicitamente com um loader sintetico nos testes.
"""

import json
import sys
from unittest.mock import Mock, call

import numpy as np
import pytest

from smarty_energy.agents import construir_agentes
from smarty_energy.environment import FazendaEnergyEnv
from smarty_energy.mcp.state import ServerState

_SERVER_MOD = "smarty_energy.mcp.server"


@pytest.fixture
def srv_sem_dados(monkeypatch):
    import importlib
    from smarty_energy import data_loader

    carregar = Mock(side_effect=AssertionError("Importacao nao deve carregar dados"))
    monkeypatch.setattr(data_loader, "carregar_dados", carregar)
    monkeypatch.delitem(sys.modules, _SERVER_MOD, raising=False)
    return importlib.import_module(_SERVER_MOD)


def test_importacao_nao_carrega_dataset(srv_sem_dados):
    srv_sem_dados.carregar_dados.assert_not_called()
    assert srv_sem_dados._state is None
    for nome in ("DIAS", "TARIFA_24H", "DATASET_META", "env", "iql", "tracker"):
        assert not hasattr(srv_sem_dados, nome)


def test_get_state_exige_initialize(srv_sem_dados):
    with pytest.raises(RuntimeError, match="chame initialize"):
        srv_sem_dados.get_state()


def test_initialize_publica_estado_com_loader(srv_sem_dados, dia_fake, tarifa_fake):
    dias = [dia_fake.copy()]
    carregar = Mock(return_value=(dias, tarifa_fake))

    srv_sem_dados.initialize(loader=carregar)

    carregar.assert_called_once_with()
    srv_sem_dados.carregar_dados.assert_not_called()
    assert srv_sem_dados._state is not None
    assert srv_sem_dados.get_state().dias is dias
    assert srv_sem_dados.get_state().tarifa_24h is tarifa_fake
    assert srv_sem_dados.get_state().dataset_meta["n_dias"] == 1
    assert srv_sem_dados.get_state().env.cfg is srv_sem_dados.CONFIG
    assert srv_sem_dados.get_state().env.hora == 0
    assert srv_sem_dados.get_state().iql.n_episodios == srv_sem_dados.N_EPISODIOS_SERVIDOR
    assert srv_sem_dados.get_state().snapshots == {}


@pytest.mark.parametrize("falha", ["leitura", "ambiente"])
def test_initialize_falha_permite_nova_tentativa(srv_sem_dados, monkeypatch, dia_fake, tarifa_fake, falha):
    carregar = Mock(return_value=([dia_fake], tarifa_fake))
    with monkeypatch.context() as contexto:
        if falha == "leitura":
            carregar.side_effect = RuntimeError("fixture-indisponivel")
        else:
            contexto.setattr(
                srv_sem_dados, "FazendaEnergyEnv",
                Mock(side_effect=RuntimeError("fixture-indisponivel")),
            )
        with pytest.raises(RuntimeError, match="fixture-indisponivel"):
            srv_sem_dados.initialize(loader=carregar)

    assert srv_sem_dados._state is None
    for nome in ("DIAS", "TARIFA_24H", "DATASET_META", "env", "iql", "tracker"):
        assert not hasattr(srv_sem_dados, nome)

    carregar.side_effect = None
    srv_sem_dados.initialize(loader=carregar)
    assert srv_sem_dados._state is not None
    assert srv_sem_dados.get_state().env.hora == 0


@pytest.mark.parametrize("argv, transporte_env, esperado", [
    ([], "streamable-http", "streamable-http"),
    (["--stdio"], "streamable-http", "stdio"),
    ([], "stdio", "stdio"),
])
def test_main_inicializa_antes_do_transporte(srv_sem_dados, monkeypatch, dia_fake, tarifa_fake, argv, transporte_env, esperado):
    carregar = Mock(return_value=([dia_fake], tarifa_fake))
    executar = Mock()
    ordem = Mock()
    ordem.attach_mock(carregar, "carregar")
    ordem.attach_mock(executar, "executar")
    monkeypatch.setattr(srv_sem_dados, "carregar_dados", carregar)
    monkeypatch.setattr(srv_sem_dados.mcp, "run", executar)
    monkeypatch.setenv("MCP_TRANSPORT", transporte_env)

    srv_sem_dados.main(argv)

    assert ordem.mock_calls == [call.carregar(), call.executar(transport=esperado)]
    assert srv_sem_dados._state is not None


def test_main_nao_inicia_transporte_se_loader_falha(srv_sem_dados, monkeypatch):
    carregar = Mock(side_effect=OSError("fixture-indisponivel"))
    executar = Mock()
    monkeypatch.setattr(srv_sem_dados, "carregar_dados", carregar)
    monkeypatch.setattr(srv_sem_dados.mcp, "run", executar)

    with pytest.raises(OSError, match="fixture-indisponivel"):
        srv_sem_dados.main([])

    executar.assert_not_called()
    assert srv_sem_dados._state is None


@pytest.fixture
def srv(monkeypatch, dia_fake, tarifa_fake):
    """Inicializa o servidor com fixtures sinteticas, sem fontes externas."""
    def fake_carregar(*_args, **_kwargs):
        return [dia_fake.copy() for _ in range(7)], tarifa_fake.copy()

    sys.modules.pop(_SERVER_MOD, None)
    import importlib
    server = importlib.import_module(_SERVER_MOD)
    server.initialize(loader=fake_carregar)

    # Garante pesos no default pra cada teste (CONFIG eh global mutavel)
    from smarty_energy.config import CONFIG
    for k, v in server._DEFAULT_REWARD_WEIGHTS.items():
        CONFIG[k] = v
        server.get_state().iql.cfg[k] = v
    yield server
    # Teardown: restaura defaults para nao vazar pesos p/ testes fora deste
    # arquivo (ex.: test_treino_converge treina com o CONFIG global).
    for k, v in server._DEFAULT_REWARD_WEIGHTS.items():
        CONFIG[k] = v
        server.get_state().iql.cfg[k] = v


# --- configure_reward_weights ----------------------------------------------

def test_estado_unico_concentra_objetos(srv):
    estado = srv.get_state()

    assert isinstance(estado, ServerState)
    assert srv.get_state() is estado
    assert estado.env.dados.equals(estado.dias[0])
    assert estado.env.tarifa is estado.tarifa_24h
    assert estado.dataset_meta["n_dias"] == len(estado.dias)
    assert estado.dia_atual_idx == 0
    assert estado.snapshots == {}
    assert estado.run_carregado is estado.experimento_carregado is None
    for nome in (
        "DIAS", "TARIFA_24H", "DATASET_META", "env", "iql", "tracker",
        "heuristico", "sem_agente", "_dia_atual_idx", "_soc_trace",
        "_soc_trace_snapshot", "_snapshots", "_rl_padrao_travado",
        "_run_carregado", "_experimento_carregado", "_initialized",
    ):
        assert not hasattr(srv, nome)


def test_estados_nao_compartilham_snapshots_por_padrao(srv):
    atual = srv.get_state()
    outro = ServerState(
        dias=atual.dias, tarifa_24h=atual.tarifa_24h, dataset_meta=atual.dataset_meta,
        iql=atual.iql, heuristico=atual.heuristico, sem_agente=atual.sem_agente,
        tracker=atual.tracker, env=atual.env,
    )

    atual.snapshots["fixture"] = {}
    atual.soc_trace = 37.5

    assert outro.snapshots == {}
    assert outro.soc_trace is None


def test_reset_atualiza_ambiente_no_mesmo_estado(srv):
    estado = srv.get_state()
    anterior = estado.env
    estado.soc_trace = 37.5
    estado.soc_trace_snapshot = 42.0

    resultado = json.loads(srv.reset_environment(dia_idx=2))

    assert resultado["status"] == "ambiente reiniciado"
    assert srv.get_state() is estado
    assert estado.env is not anterior
    assert estado.dia_atual_idx == 2
    assert estado.env.dados.equals(estado.dias[2])
    assert estado.soc_trace is estado.soc_trace_snapshot is None


def test_estado_preserva_cadeias_soc_e_snapshot_congelado(srv):
    estado = srv.get_state()
    srv._congelar_politica("fixture")
    estado.soc_trace = 40.0
    estado.soc_trace_snapshot = 70.0
    updates_antes = {nome: agente.n_updates for nome, agente in estado.iql.agentes.items()}

    snapshot = json.loads(srv.run_episode(mode="train", policy="fixture", dia_idx=0))

    assert snapshot["mode"] == "eval"
    assert snapshot["soc_inicial_pct"] == 70.0
    assert estado.soc_trace == 40.0
    assert round(estado.soc_trace_snapshot, 2) == snapshot["soc_final_pct"]
    assert {nome: agente.n_updates for nome, agente in estado.iql.agentes.items()} == updates_antes
    final_snapshot = estado.soc_trace_snapshot

    viva = json.loads(srv.run_episode(mode="eval", policy="rl_llm_mcp", dia_idx=1))

    assert viva["soc_inicial_pct"] == 40.0
    assert round(estado.soc_trace, 2) == viva["soc_final_pct"]
    assert estado.soc_trace_snapshot == final_snapshot


def test_initialize_repetido_preserva_sessao(srv):
    srv.get_state().env.step(1, 0, 2)
    srv._congelar_politica("fixture")
    srv.get_state().soc_trace = 37.5
    sessao = srv.get_state()
    estado = {nome: getattr(sessao, nome) for nome in ("dias", "env", "iql", "tracker", "snapshots")}
    carregar = Mock(side_effect=AssertionError("Nao deve reinicializar"))

    srv.initialize(loader=carregar)

    carregar.assert_not_called()
    assert srv.get_state() is sessao
    for nome, valor in estado.items():
        assert getattr(sessao, nome) is valor
    assert srv.get_state().env.hora == 1
    assert "fixture" in srv.get_state().snapshots
    assert srv.get_state().soc_trace == 37.5


def test_reward_weights_chamada_vazia_retorna_estado(srv):
    out = json.loads(srv.configure_reward_weights())
    assert out["status"] == "nenhum peso fornecido"
    assert len(out["pesos_atuais"]) == 21
    assert "defaults" in out


def test_reward_weights_valor_negativo_erra(srv):
    out = json.loads(srv.configure_reward_weights(pen_pcc=-5.0))
    assert "erro" in out
    assert "pen_pcc" in out["erro"]


def test_reward_weights_valido_persiste(srv):
    from smarty_energy.config import CONFIG
    novo = 99.0
    out = json.loads(srv.configure_reward_weights(w_custo=novo))
    assert out["status"] == "pesos atualizados"
    assert CONFIG["w_custo"] == novo
    assert out["delta_vs_default"]["w_custo"] == round(novo - 8.0, 4)
    assert "Q-tables" in out["aviso"]


def test_reward_weights_recria_env_global(srv):
    """Apos mudar peso, o ambiente ativo deve refletir o novo CONFIG."""
    env_antes = srv.get_state().env
    srv.configure_reward_weights(pen_pcc=42.0)
    assert srv.get_state().env is not env_antes  # nova instancia
    assert srv.get_state().env.cfg["pen_pcc"] == 42.0


def test_load_qtables_marca_politica_viva_como_treinada(srv, monkeypatch):
    hist = {"n_episodios": 123, "soc_final_pct": 37.5}
    monkeypatch.setattr(srv.runs, "run_mais_recente", lambda: "run_teste")
    monkeypatch.setattr(srv.runs, "carregar_run", lambda _rid, _agentes: hist)

    out = json.loads(srv.load_qtables())
    status = json.loads(srv.get_analysis_status())

    assert out["origem"] == "run_teste"
    assert out["n_episodios"] == 123
    assert status["treinado"] is True
    assert status["n_episodios"] == 123
    assert status["run_carregado"]["origem"] == "run_teste"
    assert srv.get_state().iql.soc_propagado == 37.5


def test_qtables_roundtrip_pipeline_mcp(srv, monkeypatch, tmp_path):
    monkeypatch.setattr(srv.runs, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(srv.runs, "_LATEST", tmp_path / "runs" / "latest.txt")
    originais = construir_agentes()
    estado = (0, 5, 1, 0, 0, 0)
    for agente in originais.values():
        agente.q_table[estado][:] = np.arange(agente.n_acoes, dtype=float)
    historico = {
        "n_episodios": 2, "soc_final_pct": 37.5,
        "config_completo": dict(srv.CONFIG), "rewards": [-5.0, -3.0],
    }
    run_id = srv.runs.salvar_run(originais, historico, run_id="pipeline_sintetico")

    carregado = json.loads(srv.load_qtables(run_id=run_id))
    reiniciado = json.loads(srv.reset_environment())
    salvo = json.loads(srv.save_qtables(label="fixture-sintetica"))

    assert carregado["status"] == "Q-tables carregadas"
    assert carregado["origem"] == run_id
    assert carregado["n_episodios"] == 2
    assert reiniciado["estado"]["soc"] == pytest.approx(37.5)
    assert salvo["status"] == "run salvo"
    meta = srv.runs.ler_meta(salvo["run_id"])
    assert meta["label"] == "fixture-sintetica"
    assert meta["config_completo"] == historico["config_completo"]
    restaurados = construir_agentes()
    assert srv.runs.carregar_run(salvo["run_id"], restaurados) == historico
    for nome, agente in restaurados.items():
        np.testing.assert_array_equal(agente.q_table[estado], originais[nome].q_table[estado])


def test_save_qtables_sem_treino_nao_grava(srv, monkeypatch):
    salvar = Mock(side_effect=AssertionError("Nao deve gravar sem historico"))
    monkeypatch.setattr(srv.runs, "salvar_run", salvar)

    resultado = json.loads(srv.save_qtables())

    assert "nenhum treino" in resultado["erro"]
    salvar.assert_not_called()


@pytest.mark.parametrize("acoes, parametro", [
    ((-1, 0, 0), "a_arm"), ((6, 0, 0), "a_arm"),
    ((1, -1, 0), "a_cons"), ((1, 8, 0), "a_cons"),
    ((1, 0, -1), "a_ger"), ((1, 0, 3), "a_ger"),
])
def test_step_environment_rejeita_indices_sem_avancar(srv, acoes, parametro):
    soc_inicial = srv.get_state().env.soc

    resultado = json.loads(srv.step_environment(*acoes))

    assert parametro in resultado["erro"]
    assert srv.get_state().env.hora == 0
    assert srv.get_state().env.soc == soc_inicial
    assert srv.get_state().env.historico == []


@pytest.mark.parametrize("tarifa, em_pico", [(0.70, False), (1.10, True)])
def test_step_environment_preserva_contrato_do_motor(srv, tarifa, em_pico):
    srv.get_state().tarifa_24h[:] = tarifa
    referencia = FazendaEnergyEnv(srv.get_state().dias[0], srv.get_state().tarifa_24h, srv.CONFIG)
    proximo, reward, done, info = referencia.step(5, 0, 2)

    resultado = json.loads(srv.step_environment(5, 0, 2))

    assert set(resultado) == {"reward", "done", "next_state_discrete", "obs", "info"}
    assert resultado["done"] is done is False
    assert resultado["reward"] == pytest.approx(reward, abs=1e-6)
    assert resultado["next_state_discrete"] == list(referencia.discretizar(proximo))
    assert resultado["info"]["soc"] == pytest.approx(info["soc"], abs=1e-6)
    assert isinstance(resultado["info"]["pcc_violado"], bool)
    assert resultado["info"]["em_pico_tarifa"] is em_pico
    assert srv.get_state().env.historico[-1] == info


# --- health_report: detecta pesos modificados ------------------------------

def test_get_analysis_status_representa_etapas(srv):
    inicial = json.loads(srv.get_analysis_status())
    assert inicial["proxima_etapa"] == "treinar"
    assert not inicial["treinado"]

    srv.configure_agents(n_episodios=2)
    srv.train_agents()
    apos_treino = json.loads(srv.get_analysis_status())
    # Sem passo "avaliar" separado: compare_strategies é a única medição.
    assert apos_treino["proxima_etapa"] == "comparar"
    assert apos_treino["treinado"]
    assert not apos_treino["avaliado"]

    srv.compare_strategies(n_dias=2)
    apos_comparacao = json.loads(srv.get_analysis_status())
    assert apos_comparacao["proxima_etapa"] == "investigar"
    assert apos_comparacao["avaliado"]
    assert apos_comparacao["comparado"]

    srv.snapshot_policy("rl_padrao")
    apos_snapshot = json.loads(srv.get_analysis_status())
    assert apos_snapshot["rl_padrao_congelado"]
    assert apos_snapshot["rl_padrao_travado"]

    srv.liberar_rl_padrao()
    srv.train_agents(n_episodios=2)
    apos_novo_treino = json.loads(srv.get_analysis_status())
    assert not apos_novo_treino["avaliado"]
    assert not apos_novo_treino["comparado"]
    assert apos_novo_treino["proxima_etapa"] == "comparar"

def test_health_report_sem_pesos_modificados_nao_dispara_alerta(srv):
    out = json.loads(srv.health_report())
    assert out.get("pesos_reward_modificados") is None
    assert not any("pesos_reward" in a for a in out["alertas"])


def test_health_report_com_pesos_modificados_dispara_alerta(srv):
    srv.configure_reward_weights(pen_pcc=50.0, w_custo=20.0)
    out = json.loads(srv.health_report())
    assert out["pesos_reward_modificados"] is not None
    assert "pen_pcc" in out["pesos_reward_modificados"]
    assert "w_custo" in out["pesos_reward_modificados"]
    assert any("pesos_reward_modificados" in a for a in out["alertas"])


# --- compare_strategies popula 3 trackers ----------------------------------

def test_compare_strategies_popula_quatro_trackers(srv):
    # Treina minimamente pra dar inicializacao plausivel ao IQL
    srv.configure_agents(n_episodios=2)
    srv.train_agents()

    out = json.loads(srv.compare_strategies(n_dias=2))
    assert "RL_LLM_MCP" in out
    assert "RL_padrao" in out
    assert "Heuristico" in out
    assert "SemAgente" in out
    assert "tracker_keys" in out
    assert out["tracker_keys"] == ["sem_agente", "heuristico", "rl_padrao", "rl_llm_mcp"]

    # Os 4 trackers devem ter passos registrados
    for key in out["tracker_keys"]:
        assert len(srv.get_state().tracker.passos[key]) > 0, f"tracker {key} vazio"
        assert len(srv.get_state().tracker.episodios[key]) > 0, f"episodios de {key} vazio"


def test_compare_strategies_calcula_reducoes(srv):
    srv.configure_agents(n_episodios=2)
    srv.train_agents()
    out = json.loads(srv.compare_strategies(n_dias=2))
    assert "reducao_rl_llm_vs_sem_pct" in out


def test_run_episode_greedy_usa_qtables_para_decisoes_horarias(srv):
    """O MCP executa a política IQL; ele não consulta um LLM a cada hora."""
    estado_inicial = srv.get_state().env.discretizar(srv.get_state().env.reset())
    srv.get_state().iql.agentes["armazenamento"].q_table[estado_inicial] = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
    srv.get_state().iql.agentes["consumo"].q_table[estado_inicial] = np.array([1.0] + [0.0] * 7)
    srv.get_state().iql.agentes["gerente"].q_table[estado_inicial] = np.array([0.0, 0.0, 1.0])

    resultado = json.loads(srv.run_episode(mode="eval", dia_idx=0, continuar_soc=False))
    primeiro_passo = resultado["trace"][0]

    assert (primeiro_passo["a_arm"], primeiro_passo["a_cons"], primeiro_passo["a_ger"]) == (4, 0, 2)


# --- configure_agents -------------------------------------------------------

def test_configure_agents_valida_ranges(srv):
    out = json.loads(srv.configure_agents(alpha=1.5))
    assert "erro" in out
    out = json.loads(srv.configure_agents(gamma=1.0))
    assert "erro" in out


def test_configure_agents_aceita_validos(srv):
    out = json.loads(srv.configure_agents(alpha=0.2, gamma=0.9, beta=0.05))
    assert out["status"] == "agentes reconfigurados"
    for ag in srv.get_state().iql.agentes.values():
        assert ag.alpha == 0.2
        assert ag.gamma == 0.9
        assert ag.beta == 0.05


# --- equipamentos + export --------------------------------------------------

def test_rl_padrao_sempre_presente(srv):
    srv.configure_agents(n_episodios=2)
    srv.train_agents()

    # train_agents com pesos default captura o RL padrão automaticamente.
    out = json.loads(srv.compare_strategies(n_dias=2))
    assert "RL_padrao" in out
    assert "rl_padrao" in out["tracker_keys"]
    assert len(srv.get_state().tracker.passos["rl_padrao"]) == 2 * 24
    assert "reducao_llm_vs_rl_padrao_pct" in out
    # Sem o LLM-juiz agir, RL padrão == RL + LLM MCP.
    assert abs(out["RL_padrao"]["custo_medio_dia_rs"]
               - out["RL_LLM_MCP"]["custo_medio_dia_rs"]) < 1e-6

    # health_report reflete o braço RL padrão.
    hr = json.loads(srv.health_report())
    assert hr["comparacao_baselines"]["custo_rl_padrao_rs_dia"] is not None


def test_equipment_tools_apos_compare(srv):
    srv.configure_agents(n_episodios=2)
    srv.train_agents()
    srv.compare_strategies(n_dias=2)

    for chave in ("rl_llm_mcp", "rl_padrao", "heuristico", "sem_agente"):
        stats = json.loads(srv.get_equipment_stats(chave))
        assert "equipamentos" in stats, f"stats de {chave} sem equipamentos"
        assert set(stats["equipamentos"]) == {"pivo", "captacao", "secador",
                                               "sede", "silo"}
        hourly = json.loads(srv.get_equipment_hourly(chave))
        assert "aviso" not in hourly
        assert "0" in hourly and "23" in hourly


def test_equipment_tools_sem_dados_avisa(srv):
    out = json.loads(srv.get_equipment_stats("iql_eval"))
    assert "aviso" in out


def test_battery_dispatch_tool_apos_compare(srv):
    srv.configure_agents(n_episodios=2)
    srv.train_agents()
    srv.compare_strategies(n_dias=2)

    out = json.loads(srv.get_battery_dispatch_stats("rl_llm_mcp"))

    assert "aviso" not in out
    assert set(out["bloqueios_descarga"]) == {
        "sem_deficit", "soc_minimo", "throughput_esgotado",
    }
    assert out["pedidos_descarga"] >= out["descargas_efetivas"]
    assert 0.0 <= out["pct_descarga_no_pico"] <= 100.0
    assert 0.0 <= out["taxa_descarga_efetiva_pct"] <= 100.0
    assert out["descarga_pico_media_dia_kwh"] >= 0.0
    assert out["carga_solar_ac_kwh"] >= 0.0
    assert out["carga_rede_ac_kwh"] >= 0.0
    assert out["custo_carga_rede_rs"] >= 0.0


def test_export_all_data_estrutura(srv):
    srv.configure_agents(n_episodios=2)
    srv.train_agents()
    srv.compare_strategies(n_dias=2)

    out = json.loads(srv.export_all_data())
    assert "gerado_em" in out
    assert out["dataset"]["n_dias"] == 7
    assert "config" in out and "w_custo" in out["config"]
    assert out["treino"] is not None
    assert out["curva_aprendizado"] is not None
    assert out["avaliacoes"]["rl_llm_mcp"] is not None
    assert out["avaliacoes"]["heuristico"] is not None
    assert out["equipamentos_kpis"]["sem_agente"] is not None
    assert out["equipamentos_hora_a_hora"]["rl_llm_mcp"] is not None
    # chave nunca populada fica None em vez de dict de aviso
    assert out["avaliacoes"]["iql_eval"] is None
