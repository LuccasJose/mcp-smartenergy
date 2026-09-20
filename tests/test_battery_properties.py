import pytest
from hypothesis import example, given, settings, strategies as st

from smarty_energy.battery import BatteryModel
from smarty_energy.config import CONFIG


SOC = st.floats(
    min_value=CONFIG["soc_min_pct"],
    max_value=CONFIG["soc_max_pct"],
    allow_nan=False,
    allow_infinity=False,
)
ENERGY = st.floats(min_value=0.0, max_value=100.0)
FRACTION = st.sampled_from([0.0, 0.25, 0.5, 1.0])


@settings(max_examples=100, deadline=None, derandomize=True)
@given(soc=SOC, available=ENERGY)
def test_charge_conserves_energy_and_respects_limits(soc, available):
    battery = BatteryModel(dict(CONFIG))
    battery.reset(soc)
    before = battery.soc_kwh

    flow = battery.charge(available, "solar")

    assert 0.0 <= flow.input_kwh <= available + 1e-9
    assert flow.stored_kwh == pytest.approx(
        flow.input_kwh * CONFIG["eficiencia_carga"]
    )
    assert battery.soc_kwh == pytest.approx(before + flow.stored_kwh)
    assert battery.throughput_kwh == pytest.approx(flow.stored_kwh)
    assert battery.soc_pct <= CONFIG["soc_max_pct"] + 1e-9


@settings(max_examples=100, deadline=None, derandomize=True)
@given(soc=SOC, deficit=ENERGY, fraction=FRACTION)
def test_discharge_conserves_energy_and_respects_limits(soc, deficit, fraction):
    battery = BatteryModel(dict(CONFIG))
    battery.reset(soc)
    before = battery.soc_kwh

    flow = battery.discharge(deficit, fraction)

    assert 0.0 <= flow.delivered_kwh <= deficit * fraction + 1e-9
    assert flow.delivered_kwh == pytest.approx(
        flow.input_kwh * CONFIG["eficiencia_descarga"]
    )
    assert battery.soc_kwh == pytest.approx(before - flow.input_kwh)
    assert battery.throughput_kwh == pytest.approx(flow.input_kwh)
    assert battery.soc_pct >= CONFIG["soc_min_pct"] - 1e-9


@settings(max_examples=100, deadline=None, derandomize=True)
@given(
    soc=SOC,
    operations=st.lists(st.tuples(st.booleans(), ENERGY, FRACTION), min_size=1, max_size=48),
)
@example(soc=50.0, operations=[(True, 100.0, 1.0), (False, 100.0, 1.0)] * 24)
def test_sequences_preserve_soc_and_share_dc_throughput(soc, operations):
    battery = BatteryModel(dict(CONFIG))
    battery.reset(soc)
    expected_energy = battery.soc_kwh
    expected_throughput = 0.0

    for charging, energy, fraction in operations:
        if charging:
            flow = battery.charge(energy, "rede")
            expected_energy += flow.stored_kwh
            expected_throughput += flow.stored_kwh
        else:
            flow = battery.discharge(energy, fraction)
            expected_energy -= flow.input_kwh
            expected_throughput += flow.input_kwh

        assert battery.soc_kwh == pytest.approx(expected_energy)
        assert battery.throughput_kwh == pytest.approx(expected_throughput)
        assert CONFIG["soc_min_pct"] - 1e-9 <= battery.soc_pct <= CONFIG["soc_max_pct"] + 1e-9
        assert 0.0 <= battery.throughput_kwh <= CONFIG["bat_throughput_max_kwh"] + 1e-9
