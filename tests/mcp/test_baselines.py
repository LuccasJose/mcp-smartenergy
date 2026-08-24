"""AgentesHeuristicos e SemAgente."""

from smarty_energy.agents import AgentesHeuristicos, SemAgente


def test_heuristico_decide_acao_para_estado(cfg):
    h = AgentesHeuristicos(cfg)
    est = {
        "hora": 12, "soc": 50.0, "solar_kw": 20.0, "eolico_kw": 5.0,
        "tarifa": 0.7, "stress": 30.0, "sec_ac": 0.0, "bomba_h": 0,
    }
    a_arm, a_cons, a_ger = h.agir(est)
    assert a_arm in (0, 1, 2, 3, 4)
    assert 0 <= a_cons <= 7
    assert a_ger in (0, 1, 2)


def test_heuristico_carrega_com_sol_alto_e_soc_baixo(cfg):
    """Sol alto + SOC < 80 deve disparar a_arm=0 (carregar)."""
    h = AgentesHeuristicos(cfg)
    est = {"hora": 12, "soc": 40.0, "solar_kw": 25.0, "tarifa": 0.7}
    assert h.armazenamento(est) == 0


def test_heuristico_descarrega_em_pico_tarifario(cfg):
    """Tarifa > 0.9 + SOC saudavel deve disparar descarga integral."""
    h = AgentesHeuristicos(cfg)
    est = {"hora": 18, "soc": 60.0, "solar_kw": 0.0, "tarifa": 1.10}
    assert h.armazenamento(est) == 4


def test_heuristico_consumo_corta_proporcional_ao_stress(cfg):
    """Stress crescente → mais cargas cortadas (bitmask cresce)."""
    h = AgentesHeuristicos(cfg)
    est = {}  # consumo so depende do stress
    assert h.consumo(est, 10) == 0    # sem corte
    assert h.consumo(est, 40) == 1    # corta pivo
    assert h.consumo(est, 60) == 2    # corta bomba
    assert h.consumo(est, 75) == 3    # pivo + bomba
    assert h.consumo(est, 90) == 7    # tudo


def test_heuristico_gerente_conservador_em_stress_alto(cfg):
    """Stress alto → teto conservador."""
    h = AgentesHeuristicos(cfg)
    est = {}
    assert h.gerente(est, 80) == 0    # conservador
    assert h.gerente(est, 50) == 1    # moderado
    assert h.gerente(est, 10) == 2    # liberal


# --- SemAgente --------------------------------------------------------------

def test_semagente_horarios_ingenuos(cfg):
    s = SemAgente(cfg)
    # antes das 16h: pivô segurado, bateria inerte, teto liberal
    assert s.agir({"hora": 8}) == (1, 1, 2)
    assert s.agir({"hora": 15}) == (1, 1, 2)
    # 16h em diante: pivô liberado (8h que atravessam o pico 18-20h)
    assert s.agir({"hora": 16}) == (1, 0, 2)
    assert s.agir({"hora": 20}) == (1, 0, 2)


def test_semagente_avaliar_retorna_metricas(dia_fake, tarifa_fake, cfg):
    from smarty_energy.environment import FazendaEnergyEnv
    s = SemAgente(cfg)
    metrics = s.avaliar([dia_fake], tarifa_fake, FazendaEnergyEnv, n_dias=2)
    assert metrics["n_dias"] == 2
    for k in ("custo_medio_dia_rs", "rede_media_dia_kwh",
              "violacoes_soc_media_h_dia", "reward_medio_dia"):
        assert k in metrics
