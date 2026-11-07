"""M3 gate: T6 droop, T7 unrecovered casualty, T8 recovered casualty, T11 perf.

T6 note: the analytic droop relation is evaluated against the MEASURED change
in electrical power. With an islanded bus and load frequency dependence
(k_pf = 1.5), the commanded step (+6.83 MW since 0.3.0: the non-vital block
starts at 47.17 MW after station service and is set to 54 MW) settles to a
~6.36 MW actual change (5.55 MW of a +6 MW step in 0.1.0-0.2.0);
the droop law ties frequency to actual mechanical/electrical power, so that
is the honest comparison (HANDOFF, T6 note).
"""
import time

from hotwell import data
from hotwell.simulator import Simulator

SCENARIOS = data.builtin_scenarios()


def test_t6_droop():
    sim = Simulator.from_scenario(SCENARIOS["load_step"])
    sim.run(295.0)
    f_pre = sim.last_obs.values["frequency"]
    pe_pre = sim.last_aux.p_elec
    sim.run(900.0)
    f_post = sim.last_obs.values["frequency"]
    pe_post = sim.last_aux.p_elec
    df = f_post - f_pre
    d_pe = pe_post - pe_pre
    df_analytic = -0.05 * d_pe / 60.0e6 * 60.0
    ratio = df / df_analytic
    print(f"dPe measured {d_pe / 1e6:.3f} MW; df {df:+.4f} Hz vs analytic "
          f"{df_analytic:+.4f} Hz -> {ratio * 100:.1f}%")
    assert abs(ratio - 1.0) < 0.05
    assert sim.last_obs.alarms == []  # transient FREQ_LO allowed, none expected
    assert not sim.disc.plant_dead


def test_t7_unrecovered_cascade():
    sim = Simulator.from_scenario(SCENARIOS["cp1_trip_unrecovered"])
    obs = sim.run()
    fo = sim.engine.first_out
    print("first_out:", [(f"{t:.2f}", cid) for t, cid in fo])
    # plant dies via MFT from DRUM_LVL_LOLO
    assert obs.plant_dead
    assert sim.disc.mft
    assert any(cid == "DRUM_LVL_LOLO" for _, cid in fo)
    # first-out identifies the true initiator
    assert fo[0][1] == "CP1_TRIP:overload"
    assert abs(fo[0][0] - 300.0) < 0.1
    # first PROTECTIVE trip (after the injected initiator) in the 45-120 s window
    t_first_prot = next(t for t, cid in fo if cid != "CP1_TRIP:overload")
    dt_window = t_first_prot - 300.0
    print(f"first protective trip {fo[1][1]} at +{dt_window:.2f} s after CP-1 trip")
    assert fo[1][1] == "FP1_SUCTION"
    assert 45.0 <= dt_window <= 120.0


def test_t8_recovered():
    sim = Simulator.from_scenario(SCENARIOS["cp1_trip_recovered"])
    t_start = 312.0  # scripted standby start
    sim.run(t_start + 300.0)
    v = sim.last_obs.values
    print(f"levels at +300 s: drum {v['drum_level'] * 1e3:+.1f} mm, "
          f"DA {v['da_level']:+.3f} m, HW {v['hotwell_level']:+.3f} m; "
          f"first_out={sim.engine.first_out}")
    # zero trips: only the scenario-injected CP-1 trip appears
    assert [cid for _, cid in sim.engine.first_out] == ["CP1_TRIP:overload"]
    assert not sim.disc.mft and not sim.disc.turbine_trip
    assert sim.disc.pump_modes["cp2"] == "running"
    # steady bands re-established within 300 s of the standby start
    assert abs(v["drum_level"]) < 0.05
    assert abs(v["da_level"]) < 0.10
    assert abs(v["hotwell_level"]) < 0.10
    assert abs(v["frequency"] - 60.0) < 0.05
    obs = sim.run(900.0)
    assert not obs.plant_dead
    assert [cid for _, cid in sim.engine.first_out] == ["CP1_TRIP:overload"]


def test_t11_performance():
    sim = Simulator(seed=0)
    sim.initialize_steady_state(60.0)
    wall0 = time.perf_counter()
    sim.run(3600.0)
    wall = time.perf_counter() - wall0
    print(f"1 h simulated in {wall:.1f} s wall ({3600.0 / wall:.0f}x real time)")
    assert sim.t >= 3599.9
    assert wall <= 60.0
