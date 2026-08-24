"""Tools do servidor MCP (configure_*, compare_strategies, health_report).

O servidor real carrega o dataset no import. Para isolar, monkey-patchamos
`carregar_dados` antes de re-importar o modulo do servidor.
"""

import json
import sys

import numpy as np
import pytest

_SERVER_MOD = "smarty_energy.mcp.server"


@pytest.fixture
def srv(monkeypatch, dia_fake, tarifa_fake):
    """Importa o servidor com o dataset substituido por fixtures sinteticas."""
    from smarty_energy import data_loader

    def fake_carregar(*_args, **_kwargs):
        return [dia_fake.copy() for _ in range(7)], tarifa_fake.copy()

    monkeypatch.setattr(data_loader, "carregar_dados", fake_carregar)
    sys.modules.pop(_SERVER_MOD, None)
    import importlib
    server = importlib.import_module(_SERVER_MOD)

    # Garante pesos no default pra cada teste (CONFIG eh global mutavel)
    from smarty_energy.config import CONFIG
    for k, v in server._DEFAULT_REWARD_WEIGHTS.items():
        CONFIG[k] = v
        server.iql.cfg[k] = v
    return server


# --- configure_reward_weights ----------------------------------------------

def test_reward_weights_chamada_vazia_retorna_estado(srv):
    out = json.loads(srv.configure_reward_weights())
    assert out["status"] == "nenhum peso fornecido"
    assert len(out["pesos_atuais"]) == 16
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
    """Apos mudar peso, env global deve refletir o novo CONFIG."""
    env_antes = srv.env
    srv.configure_reward_weights(pen_pcc=42.0)
    assert srv.env is not env_antes  # nova instancia
    assert srv.env.cfg["pen_pcc"] == 42.0


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
    assert srv.iql.soc_propagado == 37.5


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
        assert len(srv.tracker.passos[key]) > 0, f"tracker {key} vazio"
        assert len(srv.tracker.episodios[key]) > 0, f"episodios de {key} vazio"


def test_compare_strategies_calcula_reducoes(srv):
    srv.configure_agents(n_episodios=2)
    srv.train_agents()
    out = json.loads(srv.compare_strategies(n_dias=2))
    assert "reducao_rl_llm_vs_sem_pct" in out


def test_run_episode_greedy_usa_qtables_para_decisoes_horarias(srv):
    """O MCP executa a política IQL; ele não consulta um LLM a cada hora."""
    estado_inicial = srv.env.discretizar(srv.env.reset())
    srv.iql.agentes["armazenamento"].q_table[estado_inicial] = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
    srv.iql.agentes["consumo"].q_table[estado_inicial] = np.array([1.0] + [0.0] * 7)
    srv.iql.agentes["gerente"].q_table[estado_inicial] = np.array([0.0, 0.0, 1.0])

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
    for ag in srv.iql.agentes.values():
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
    assert len(srv.tracker.passos["rl_padrao"]) == 2 * 24
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
