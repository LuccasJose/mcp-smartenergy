"""MetricsTracker."""

def _info_passo(hora: int, soc: float = 50.0, pcc_violado: bool = False,
                em_pico_tarifa: bool = False, custo_r: float = 1.0,
                rede_kwh: float = 5.0, kwh_cortado: float = 0.0,
                teto_excedido: bool = False) -> dict:
    return {
        "hora": hora, "soc": soc, "pcc_violado": pcc_violado,
        "em_pico_tarifa": em_pico_tarifa, "custo_r": custo_r,
        "rede_kwh": rede_kwh, "kwh_cortado": kwh_cortado,
        "teto_excedido": teto_excedido,
        "pivo_kw_consumido": 3.0, "captacao_kw_consumido": 15.0,
        "secador_kw_consumido": 2.2, "sede_kw_consumido": 1.0,
        "silo_kw_consumido": 0.5,
    }


def test_registrar_passo_e_fechar_episodio(tracker):
    for h in range(24):
        tracker.registrar_passo(_info_passo(h), agente="a")
    tracker.fechar_episodio(agente="a", reward_total=-100.0, custo_total=50.0,
                             epsilon=0.5, cenario="REAL")
    assert len(tracker.passos["a"]) == 24
    assert len(tracker.episodios["a"]) == 1


def test_hourly_violations_agrega_por_hora(tracker):
    # Hora 0: 2 passos sem violacao
    tracker.registrar_passo(_info_passo(0, soc=80.0), agente="a")
    tracker.registrar_passo(_info_passo(0, soc=80.0), agente="a")
    # Hora 18: 1 passo com PCC violado e SOC critico
    tracker.registrar_passo(_info_passo(18, soc=10.0, pcc_violado=True), agente="a")

    h = tracker.get_hourly_violations("a")
    assert h[0]["n_observacoes"] == 2
    assert h[0]["violacoes_soc"] == 0
    assert h[0]["violacoes_pcc"] == 0
    assert h[18]["n_observacoes"] == 1
    assert h[18]["violacoes_pcc"] == 1
    assert h[18]["violacoes_soc"] == 1


def test_hourly_violations_vazio(tracker):
    h = tracker.get_hourly_violations("inexistente")
    assert "aviso" in h


def test_peak_offpeak_separa_por_tarifa(tracker):
    # 2 passos pico + 3 passos fora-pico
    for _ in range(2):
        tracker.registrar_passo(_info_passo(18, em_pico_tarifa=True, custo_r=5.0),
                                 agente="a")
    for _ in range(3):
        tracker.registrar_passo(_info_passo(12, em_pico_tarifa=False, custo_r=1.0),
                                 agente="a")
    stats = tracker.get_peak_offpeak_stats("a")
    assert stats["pico"]["n_horas"] == 2
    assert stats["fora_pico"]["n_horas"] == 3
    assert abs(stats["pico"]["custo_rs"] - 10.0) < 1e-9
    assert abs(stats["fora_pico"]["custo_rs"] - 3.0) < 1e-9


def test_get_eval_metrics_calcula_media(tracker):
    tracker.registrar_passo(_info_passo(0, custo_r=1.0, rede_kwh=10.0), agente="a")
    tracker.registrar_passo(_info_passo(1, custo_r=2.0, rede_kwh=20.0), agente="a")
    tracker.fechar_episodio(agente="a", reward_total=-3.0, custo_total=3.0,
                             epsilon=0.1, cenario="REAL")
    m = tracker.get_eval_metrics("a")
    assert m["n_dias"] == 1
    assert abs(m["custo_medio_dia_rs"] - 3.0) < 1e-9
    assert m["violacoes_pcc_total"] == 0
    assert m["violacoes_soc_total_h"] == 0


def test_limpar_por_chave(tracker):
    tracker.registrar_passo(_info_passo(0), agente="a")
    tracker.registrar_passo(_info_passo(0), agente="b")
    tracker.limpar("a")
    assert tracker.passos["a"] == []
    assert len(tracker.passos["b"]) == 1
