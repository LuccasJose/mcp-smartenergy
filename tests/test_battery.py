import pytest

from smarty_energy.battery import BatteryModel
from smarty_energy.config import CONFIG


@pytest.fixture
def cfg():
    return dict(CONFIG)


def test_carga_respeita_eficiencia_e_origem(cfg):
    battery = BatteryModel(cfg)
    battery.reset(soc_inicial=50.0)

    flow = battery.charge(10.0, "solar")

    assert flow.source == "solar"
    assert flow.input_kwh == pytest.approx(10.0)
    assert flow.stored_kwh == pytest.approx(10.0 * cfg["eficiencia_carga"])
    assert battery.soc_kwh == pytest.approx(12.0 + flow.stored_kwh)
    assert battery.throughput_kwh == pytest.approx(flow.stored_kwh)


def test_descarga_respeita_eficiencia_e_limite_minimo(cfg):
    battery = BatteryModel(cfg)
    battery.reset(soc_inicial=50.0)

    flow = battery.discharge(5.0, 1.0)

    assert flow.requested_kwh == pytest.approx(5.0)
    assert flow.input_kwh == pytest.approx(5.0 / cfg["eficiencia_descarga"])
    assert flow.delivered_kwh == pytest.approx(5.0)
    assert battery.soc_pct > cfg["soc_min_pct"]
    assert battery.throughput_kwh == pytest.approx(flow.input_kwh)


def test_carga_limita_por_soc_maximo(cfg):
    battery = BatteryModel(cfg)
    battery.reset(soc_inicial=94.0)

    flow = battery.charge(10.0, "rede")

    assert flow.source == "rede"
    assert flow.stored_kwh == pytest.approx(battery.soc_max_kwh - 0.94 * cfg["bateria_cap_kwh"])
    assert battery.soc_pct == pytest.approx(cfg["soc_max_pct"])
    assert flow.blocked_reason is None


def test_descarga_limita_por_soc_minimo(cfg):
    battery = BatteryModel(cfg)
    battery.reset(soc_inicial=16.0)

    flow = battery.discharge(10.0, 1.0)

    assert flow.delivered_kwh == pytest.approx(
        (0.16 - cfg["soc_min_pct"] / 100.0) * cfg["bateria_cap_kwh"]
        * cfg["eficiencia_descarga"]
    )
    assert battery.soc_pct == pytest.approx(cfg["soc_min_pct"])


def test_throughput_e_compartilhado_por_carga_e_descarga(cfg):
    limited = dict(cfg, bat_throughput_max_kwh=1.0)
    battery = BatteryModel(limited)
    battery.reset(soc_inicial=50.0)

    charge = battery.charge(10.0, "rede")
    discharge = battery.discharge(10.0, 1.0)

    assert charge.stored_kwh == pytest.approx(1.0)
    assert discharge.blocked_reason == "throughput_esgotado"
    assert discharge.delivered_kwh == pytest.approx(0.0)
    assert battery.throughput_kwh == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("operation", "expected"),
    (("charge", "sem_energia_disponivel"), ("discharge", "sem_deficit")),
)
def test_operacao_sem_energia_e_bloqueada(cfg, operation, expected):
    battery = BatteryModel(cfg)
    flow = battery.charge(0.0, "rede") if operation == "charge" else battery.discharge(0.0, 1.0)

    assert flow.blocked_reason == expected
    assert battery.throughput_kwh == pytest.approx(0.0)


def test_carga_bloqueada_no_soc_maximo_e_no_throughput(cfg):
    full = BatteryModel(cfg)
    full.reset(soc_inicial=cfg["soc_max_pct"])
    assert full.charge(1.0, "rede").blocked_reason == "soc_maximo"

    exhausted = BatteryModel(dict(cfg, bat_throughput_max_kwh=0.0))
    assert exhausted.charge(1.0, "rede").blocked_reason == "throughput_esgotado"


def test_descarga_bloqueada_no_soc_minimo_e_no_throughput(cfg):
    empty = BatteryModel(cfg)
    empty.reset(soc_inicial=cfg["soc_min_pct"])
    assert empty.discharge(1.0, 1.0).blocked_reason == "soc_minimo"

    exhausted = BatteryModel(dict(cfg, bat_throughput_max_kwh=0.0))
    assert exhausted.discharge(1.0, 1.0).blocked_reason == "throughput_esgotado"


def test_reset_preserva_soc_informado_e_renova_throughput(cfg):
    battery = BatteryModel(dict(cfg, bat_throughput_max_kwh=1.0))
    battery.charge(10.0, "solar")
    soc_final = battery.soc_pct
    assert battery.throughput_remaining_kwh == pytest.approx(0.0)

    battery.reset(soc_inicial=soc_final)

    assert battery.soc_pct == pytest.approx(soc_final)
    assert battery.throughput_kwh == pytest.approx(0.0)
    assert battery.charge(10.0, "solar").stored_kwh == pytest.approx(1.0)

    battery.reset()
    assert battery.soc_pct == pytest.approx(cfg["soc_inicial_pct"])
    assert battery.throughput_kwh == pytest.approx(0.0)
