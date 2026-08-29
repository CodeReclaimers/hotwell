"""Station-service pump motor loads on the islanded bus (0.3.0).

Running pump motors draw from the generator. At init the abstract load blocks
absorb ``load_mw - station_service``, so the commanded GROSS output and the
60 Hz droop equilibrium are preserved exactly — the PLAN-panel §5.1 anchors
(76.9 kg/s steam, 87.1 kg/s feed, 60.0 MW at 60.00 Hz) are unchanged. What
changes is the dynamics: starting or losing a pump now moves the MW meter.
"""
from __future__ import annotations

import pytest

from hotwell.plant import load_config
from hotwell.simulator import Simulator


@pytest.fixture(scope="module")
def sim60():
    sim = Simulator(seed=0)
    sim.initialize_steady_state(60.0)
    return sim


def test_init_preserves_gross_output_and_anchors(sim60):
    """Blocks absorb the pump draw; gross = load_mw at f0 exactly."""
    aux = sim60.last_aux
    v = sim60.last_obs.values
    p_blocks = sim60.plant.loads.vital.p0 + sim60.plant.loads.nonvital.p0
    print(f"\n  p_elec {aux.p_elec / 1e6:.6f} MW | station service "
          f"{aux.p_station_service / 1e3:.2f} kW | blocks {p_blocks / 1e6:.4f} MW")
    print(f"  sensed: mw_out {v['mw_out'] / 1e6:.3f} MW, freq {v['frequency']:.4f} Hz, "
          f"steam {v['steam_flow']:.3f}, feed {v['feed_flow']:.3f} kg/s")
    assert aux.p_elec == pytest.approx(60.0e6, abs=1.5e3)   # 1 kW fixed point
    assert v["mw_out"] == pytest.approx(60.0e6, abs=1e5)    # display: 60.0 MW
    assert v["frequency"] == pytest.approx(60.0, abs=1e-3)
    # §5.1 anchors, exactly as before station service existed:
    assert v["steam_flow"] == pytest.approx(76.9, abs=0.05)
    assert v["feed_flow"] == pytest.approx(87.1, abs=0.05)
    # one CP + one FP running at the design point:
    assert 0.9e6 < aux.p_station_service < 1.2e6
    assert p_blocks == pytest.approx(60.0e6 - aux.p_station_service, abs=1.5e3)
    assert sim60.steady_state_residual_norm() < 1e-7


def test_second_feed_pump_visibly_loads_the_generator():
    """FP-2 start: parallel operation raises total motor draw ~0.5 MW."""
    sim = Simulator(seed=0)
    sim.initialize_steady_state(60.0)
    sim.run(5.0)
    p0, ss0 = sim.last_aux.p_elec, sim.last_aux.p_station_service
    sim.apply_actions({"fp2.start": True})
    sim.run(65.0)   # spin-up (tau 4 s) + governor settle
    aux = sim.last_aux
    d_ss = aux.p_station_service - ss0
    print(f"\n  FP-2 start: p_elec {p0 / 1e6:.3f} -> {aux.p_elec / 1e6:.3f} MW, "
          f"station service +{d_ss / 1e3:.1f} kW, "
          f"freq {sim.last_obs.values['frequency']:.3f} Hz")
    # ~0.25 MW settled (3E control pulls the FRV back, lowering per-pump
    # flow); transiently higher during the swap.
    assert 0.15e6 < d_ss < 0.9e6
    assert aux.p_elec - p0 > 0.2e6, "the MW meter must move (0.1 MW resolution)"


def test_second_condensate_pump_draw_is_real_but_small():
    """CP-2 start: tens of kW — honest for a 40 m head condensate system,
    below the 0.1 MW meter resolution (the ammeter is the visible cue)."""
    sim = Simulator(seed=0)
    sim.initialize_steady_state(60.0)
    sim.run(5.0)
    ss0 = sim.last_aux.p_station_service
    sim.apply_actions({"cp2.start": True})
    sim.run(35.0)
    d_ss = sim.last_aux.p_station_service - ss0
    print(f"\n  CP-2 start: station service +{d_ss / 1e3:.2f} kW")
    assert 5e3 < d_ss < 40e3


def test_tripped_pump_draws_nothing_while_coasting(sim60):
    """Contactor opens on trip: no draw even at full coast speed."""
    sim = sim60
    ss_before = sim.last_aux.p_station_service
    saved = sim.disc.pump_modes["fp1"]
    try:
        sim.disc.pump_modes["fp1"] = "tripped"
        _, aux = sim.plant.deriv(sim.y, sim.commands, sim.disc)
        s = sim.y[sim.plant.pumps["fp1"].i_s]
        print(f"\n  fp1 tripped at s={s:.2f}: station service "
              f"{ss_before / 1e3:.1f} -> {aux.p_station_service / 1e3:.1f} kW")
        assert s > 0.9, "precondition: still spinning"
        assert aux.p_station_service < 0.1e6   # only the CP remains
    finally:
        sim.disc.pump_modes["fp1"] = saved


def test_dead_bus_carries_no_station_service(sim60):
    """Breaker open -> p_elec 0, pumps included (D10 dead bus)."""
    sim = sim60
    saved = sim.disc.breaker_closed
    try:
        sim.disc.breaker_closed = False
        _, aux = sim.plant.deriv(sim.y, sim.commands, sim.disc)
        assert aux.p_elec == 0.0
    finally:
        sim.disc.breaker_closed = saved


def test_zero_motor_rating_restores_pre_030_behavior():
    """p_motor_rated 0 disables the feature: blocks carry the full load."""
    cfg = load_config()
    cfg["pumps"]["condensate"]["p_motor_rated"] = 0.0
    cfg["pumps"]["feed"]["p_motor_rated"] = 0.0
    sim = Simulator(config=cfg, seed=0)
    sim.initialize_steady_state(60.0)
    aux = sim.last_aux
    p_blocks = sim.plant.loads.vital.p0 + sim.plant.loads.nonvital.p0
    print(f"\n  disabled: p_ss {aux.p_station_service:.1f} W, "
          f"blocks {p_blocks / 1e6:.4f} MW, p_elec {aux.p_elec / 1e6:.6f} MW")
    assert aux.p_station_service == 0.0
    assert p_blocks == pytest.approx(60.0e6, abs=1.0)
    assert aux.p_elec == pytest.approx(60.0e6, abs=1e3)
