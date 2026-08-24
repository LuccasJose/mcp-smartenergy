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


def test_battery_dispatch_stats_separa_pico_e_motivos_de_bloqueio(tracker):
    tracker.registrar_passo({
        **_info_passo(18, em_pico_tarifa=True), "a_arm": 2,
        "bat_descarga": 3.0, "bat_carga": 0.0,
        "motivo_descarga_bloqueada": None,
    }, agente="a")
    tracker.registrar_passo({
        **_info_passo(19, em_pico_tarifa=True), "a_arm": 2,
        "bat_descarga": 0.0, "bat_carga": 0.0,
        "motivo_descarga_bloqueada": "soc_minimo",
    }, agente="a")
    tracker.registrar_passo({
        **_info_passo(12), "a_arm": 0,
        "bat_descarga": 0.0, "bat_carga": 2.0,
        "motivo_descarga_bloqueada": None,
    }, agente="a")
    tracker.registrar_passo({
        **_info_passo(20, soc=40.0, em_pico_tarifa=True), "a_arm": 1,
        "bat_descarga": 0.0, "bat_carga": 0.0,
        "motivo_descarga_bloqueada": None,
    }, agente="a")

    stats = tracker.get_battery_dispatch_stats("a")

    assert stats["pedidos_descarga"] == 2
    assert stats["pedidos_por_nivel"] == {2: 2, 3: 0, 4: 0}
    assert stats["descargas_efetivas"] == 1
    assert stats["descarga_pico_kwh"] == 3.0
    assert stats["carga_fora_pico_kwh"] == 2.0
    assert stats["bloqueios_descarga"]["soc_minimo"] == 1
    assert stats["pct_descarga_no_pico"] == 100.0
    assert stats["taxa_descarga_efetiva_pct"] == 50.0
    assert stats["descarga_pico_media_dia_kwh"] == 3.0
    assert stats["soc_medio_apos_18h_pct"] == 50.0
    assert stats["soc_medio_apos_20h_pct"] == 40.0


def test_battery_dispatch_stats_separa_origem_e_custo_da_carga(tracker):
    tracker.registrar_passo({
        **_info_passo(10), "tarifa": 0.70, "carga_solar_ac": 2.0,
        "carga_rede_ac": 3.0, "bloqueio_carga_rede": None,
    }, agente="a")
    tracker.registrar_passo({
        **_info_passo(18, em_pico_tarifa=True), "tarifa": 1.10,
        "carga_rede_ac": 0.0, "bloqueio_carga_rede": "tarifa_alta",
    }, agente="a")

    stats = tracker.get_battery_dispatch_stats("a")

    assert stats["carga_solar_ac_kwh"] == 2.0
    assert stats["carga_rede_ac_kwh"] == 3.0
    assert stats["custo_carga_rede_rs"] == 2.1
    assert stats["bloqueios_carga_rede"]["tarifa_alta"] == 1


def test_equipment_hourly_agrega_medias(tracker):
    tracker.registrar_passo({**_info_passo(0), "pivo_kw_consumido": 2.0}, agente="a")
    tracker.registrar_passo({**_info_passo(0), "pivo_kw_consumido": 4.0}, agente="a")
    tracker.registrar_passo(_info_passo(5), agente="a")

    h = tracker.get_equipment_hourly("a")
    assert h[0]["n_observacoes"] == 2
    assert abs(h[0]["pivo"] - 3.0) < 1e-9          # média de 2.0 e 4.0
    assert abs(h[5]["captacao"] - 15.0) < 1e-9
    assert 5 in h and 1 not in h


def test_equipment_hourly_vazio(tracker):
    assert "aviso" in tracker.get_equipment_hourly("inexistente")


def test_equipment_stats_kpis(tracker):
    # 1 dia: pivô ligado 2h (1 em pico com tarifa 1.10, 1 fora com 0.70)
    p1 = {**_info_passo(18, em_pico_tarifa=True), "tarifa": 1.10}
    p2 = {**_info_passo(10, em_pico_tarifa=False), "tarifa": 0.70}
    p3 = {**_info_passo(3), "pivo_kw_consumido": 0.0, "tarifa": 0.70}
    for p in (p1, p2, p3):
        tracker.registrar_passo(p, agente="a")
    tracker.fechar_episodio(agente="a", reward_total=-1.0, custo_total=1.0,
                             epsilon=0.1)

    stats = tracker.get_equipment_stats("a")
    pivo = stats["equipamentos"]["pivo"]
    assert stats["n_dias"] == 1
    assert abs(pivo["kwh_total"] - 6.0) < 1e-9        # 3.0 + 3.0
    assert pivo["horas_ligada_total"] == 2
    assert abs(pivo["kwh_em_pico"] - 3.0) < 1e-9
    assert abs(pivo["pct_kwh_em_pico"] - 50.0) < 1e-9
    assert abs(pivo["custo_energia_rs"] - (3.0 * 1.10 + 3.0 * 0.70)) < 1e-9
    assert stats["consumo_total_kwh"] > 0


def test_equipment_stats_vazio(tracker):
    assert "aviso" in tracker.get_equipment_stats("inexistente")


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
