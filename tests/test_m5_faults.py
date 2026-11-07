"""0.4.0 M5: hidden physical faults. For each: zero-magnitude identity,
signature direction (with a predicted magnitude where one exists), and
mass/energy audit closure under the fault."""
import numpy as np
import pytest

from hotwell.plant import load_config
from hotwell.scenario import Scenario, ScenarioEvent, load_scenario
from hotwell.simulator import Simulator


def _sim(events=(), cfg=None, max_t=900.0, seed=1):
    sc = Scenario(name="m5", seed=seed, load_mw=60.0, mode="islanded",
                  events=tuple(sorted(events, key=lambda e: e.t)), max_t=max_t)
    sim = Simulator(cfg or load_config(), scenario=sc)
    sim.initialize_steady_state(60.0)
    return sim


def _run(sim, until):
    while sim.t < until - 0.5 * sim.dt:
        sim.step()
    return sim


def _x(sim, name):
    return float(sim.y[getattr(sim.plant, name).i_x])


def _audit_ok(sim, label):
    rep = sim.audit()
    print(f"  [{label}] audit: mass drift {rep.mass_drift_frac:.2e}, "
          f"energy residual {rep.energy_residual_frac:.2e} of firing")
    assert abs(rep.mass_drift_frac) < 1e-6
    assert abs(rep.energy_residual_frac) < 1e-3


BASE = None


def _baseline(until=900.0):
    global BASE
    if BASE is None:
        BASE = _run(_sim(), until)
    return BASE


# ---------------------------------------------------------------- identity

@pytest.mark.parametrize("ev", [
    ScenarioEvent(10.0, "pump_degrade", {"target": "fp1", "head_factor": 1.0}),
    ScenarioEvent(10.0, "valve_degrade", {"target": "frv", "cv_factor": 1.0, "ramp_s": 30.0}),
    ScenarioEvent(10.0, "actuator_slow", {"target": "throttle", "rate_factor": 1.0}),
    ScenarioEvent(10.0, "firing_degrade", {"eta_factor": 1.0}),
    ScenarioEvent(10.0, "condenser_fouling", {"slope_factor": 1.0, "ramp_s": 5.0}),
], ids=lambda e: e.type)
def test_zero_magnitude_fault_is_bit_identical(ev):
    a = _run(_sim(max_t=120.0), 120.0)
    b = _run(_sim([ev], max_t=120.0), 120.0)
    print(f"\n{ev.type}: state {a.state_history_hash[:16]} vs {b.state_history_hash[:16]}")
    assert a.state_history_hash == b.state_history_hash
    assert a.observation_hash == b.observation_hash


# --------------------------------------------------------------- signatures

def test_pump_degrade_opens_frv_and_shows_only_while_that_pump_runs():
    """FP-1 head -3 %: the FRV opens further to hold the same feed flow (the
    valve's share of the pump-to-drum drop shrinks), and FP-1 draws less
    current at the lower head. Swapping to the healthy FP-2 restores the
    baseline FRV position, so the fault is visible only while FP-1 runs."""
    base = _baseline()
    sim = _sim([ScenarioEvent(10.0, "pump_degrade", {"target": "fp1", "head_factor": 0.97}),
                ScenarioEvent(900.0, "action", {"command": {"fp2.start": True}}),
                ScenarioEvent(960.0, "action", {"command": {"fp1.stop": True}})],
               max_t=1800.0)
    _run(sim, 900.0)
    x_deg, i_deg = _x(sim, "fw_valve"), sim.last_obs.values["fp1_current"]
    feed_deg = sim.last_aux.m_fw
    _audit_ok(sim, "pump_degrade")
    _run(sim, 1800.0)
    x_swap = _x(sim, "fw_valve")
    x0, i0 = _x(base, "fw_valve"), base.last_obs.values["fp1_current"]
    print(f"\nFRV x: healthy {x0:.4f}, FP-1 at 97 % head {x_deg:.4f}, after swap to FP-2 "
          f"{x_swap:.4f}; FP-1 current {i0:.0f} -> {i_deg:.0f} A; feed "
          f"{base.last_aux.m_fw:.3f} -> {feed_deg:.3f} kg/s; rejected {sim.rejected}")
    assert x_deg > x0 + 0.05
    assert i_deg < i0
    assert feed_deg == pytest.approx(base.last_aux.m_fw, abs=0.05)
    assert x_swap == pytest.approx(x0, abs=0.005)
    assert not sim.rejected


@pytest.mark.parametrize(("target", "act"), [("frv", "fw_valve"), ("lcv", None)])
def test_valve_degrade_position_scales_inversely_with_cv(target, act):
    """At the same flow and (to first order) the same drop, x * Cv is
    constant, so Cv * 0.8 means position * 1.25."""
    base = _baseline()
    sim = _run(_sim([ScenarioEvent(10.0, "valve_degrade",
                                   {"target": target, "cv_factor": 0.8})]), 900.0)
    if act:
        x0, x1 = _x(base, act), _x(sim, act)
    else:
        x0, x1 = base.commands.lcv_x, sim.commands.lcv_x
    print(f"\n{target}: position {x0:.4f} -> {x1:.4f}, ratio {x1 / x0:.4f} (1/0.8 = 1.25)")
    assert x1 / x0 == pytest.approx(1.25, rel=0.02)
    _audit_ok(sim, f"valve_degrade {target}")


def test_actuator_stuck_freezes_position_while_controller_output_diverges():
    ev = [ScenarioEvent(10.0, "actuator_stuck", {"target": "fw_valve", "t_end": 200.0}),
          ScenarioEvent(20.0, "set_load", {"target": "nonvital", "p0": 51.0e6})]
    sim = _sim(ev, max_t=400.0)
    _run(sim, 10.0)
    x_frozen = _x(sim, "fw_valve")
    gap = 0.0
    while sim.t < 199.0:
        sim.step()
        assert _x(sim, "fw_valve") == x_frozen
        gap = max(gap, abs(sim.control.drum_level.output - x_frozen))
    lvl_stuck = sim.last_aux.drum_level
    _run(sim, 400.0)
    print(f"\nFRV frozen at {x_frozen:.4f} for 190 s; controller output gap up to {gap:.3f}; "
          f"true level at release {lvl_stuck * 1e3:+.1f} mm; after release FRV "
          f"{_x(sim, 'fw_valve'):.4f}, level {sim.last_aux.drum_level * 1e3:+.1f} mm")
    assert gap > 0.02
    assert _x(sim, "fw_valve") != x_frozen      # t_end released it
    assert abs(sim.last_aux.drum_level) < abs(lvl_stuck)


def test_stuck_da_lcv_holds_command_and_sensed_position():
    ev = [ScenarioEvent(10.0, "actuator_stuck", {"target": "da_lcv"}),
          ScenarioEvent(20.0, "set_load", {"target": "nonvital", "p0": 51.0e6})]
    sim = _sim(ev, max_t=300.0)
    _run(sim, 10.0)
    held = sim.commands.lcv_x
    sensed = set()
    while sim.t < 300.0:
        sim.step()
        sensed.add(sim.last_obs.values["da_lcv_pos"])
    print(f"\nLCV held at {held:.4f}; sensed positions seen {sorted(sensed)}; DA PI output "
          f"{sim.control.da_level.output:.4f}; DA level {sim.last_obs.values['da_level']:+.3f} m")
    assert sim.commands.lcv_x == held
    assert len(sensed) == 1
    assert abs(sim.control.da_level.output - held) > 0.01


def _throttle_step_run(rate_factor):
    step = ScenarioEvent(30.0, "set_load", {"target": "nonvital", "p0": 54.0e6})
    extra = [] if rate_factor is None else [ScenarioEvent(
        10.0, "actuator_slow", {"target": "throttle", "rate_factor": rate_factor})]
    sim = _sim([step, *extra], max_t=200.0)
    _run(sim, 29.0)
    x_prev, rate, fmin, fmax = _x(sim, "throttle"), 0.0, 99.0, 0.0
    while sim.t < 200.0:
        sim.step()
        x = _x(sim, "throttle")
        rate = max(rate, abs(x - x_prev) / sim.dt)
        x_prev = x
        f = sim.y[sim.plant.turbine.i_omega] / (2 * np.pi)
        fmin, fmax = min(fmin, f), max(fmax, f)
    return sim, rate, fmin, fmax


def test_actuator_slow_limits_slew_and_deepens_the_frequency_dip():
    """Throttle slew 1.0/s -> 0.05/s, +6 MW step. The droop governor's demand
    gets to the valve late, so frequency dips further; no protective action."""
    _, r0, f0, _ = _throttle_step_run(None)
    sim, r1, f1, _ = _throttle_step_run(0.05)
    print(f"\nthrottle max slew healthy {r0:.3f}/s, slow {r1:.4f}/s; min frequency "
          f"healthy {f0:.3f} Hz, slow {f1:.3f} Hz; first_out {sim.engine.first_out}")
    assert r1 <= 0.05 + 1e-9
    assert f1 < f0 - 0.05
    assert not sim.engine.first_out


def test_very_slow_throttle_turns_a_load_step_into_an_overspeed_trip():
    """At 0.02/s the dip reaches the 58.8 Hz underfrequency shed, which drops
    the 54 MW non-vital block; the throttle can't close fast enough and the
    rotor overspeeds into a turbine trip (measured 2026-11-07: 58.742 Hz min,
    68.03 Hz max, OVERSPEED at t = 35.6 s). The one-step throttle "jump" is
    the D12 trip slam, not a broken rate limit."""
    sim, _, fmin, fmax = _throttle_step_run(0.02)
    fo = [c for _, c in sim.engine.first_out]
    print(f"\nf {fmin:.3f}..{fmax:.3f} Hz; first_out {fo}; nonvital "
          f"{sim.disc.nonvital_connected}")
    assert fmin < 58.8 and not sim.disc.nonvital_connected
    assert fo[0] == "OVERSPEED"
    assert sim.disc.turbine_trip


def test_firing_degrade_raises_firing_rate_by_one_over_eta():
    base = _baseline()
    sim = _run(_sim([ScenarioEvent(10.0, "firing_degrade",
                                   {"eta_factor": 0.95, "ramp_s": 60.0})]), 900.0)
    x0, x1 = _x(base, "firing"), _x(sim, "firing")
    print(f"\nfiring x {x0:.4f} -> {x1:.4f}, ratio {x1 / x0:.4f} (1/0.95 = {1 / 0.95:.4f}); "
          f"drum p {sim.last_aux.p_drum / 1e6:.4f} MPa; q_fire {base.last_aux.q_fire / 1e6:.3f} "
          f"-> {sim.last_aux.q_fire / 1e6:.3f} MW")
    assert x1 / x0 == pytest.approx(1 / 0.95, rel=0.005)
    assert sim.last_aux.p_drum == pytest.approx(8.0e6, rel=1e-3)
    _audit_ok(sim, "firing_degrade")


def test_condenser_fouling_raises_backpressure_in_proportion_to_load():
    """slope * 3: dp_cond = 2 * p_load_slope * m_exh/m_rated (about +3 kPa at
    rated), unlike air ingress, which is load-independent. Lost output via M2."""
    base = _baseline()
    sim = _run(_sim([ScenarioEvent(10.0, "condenser_fouling", {"slope_factor": 3.0})]), 900.0)
    c = sim.cfg["condenser"]
    pred = 2.0 * c["p_load_slope"] * sim.last_aux.m_exhaust / c["m_exh_rated"] \
        + c["p_load_slope"] * (sim.last_aux.m_exhaust - base.last_aux.m_exhaust) / c["m_exh_rated"]
    dp = sim.last_aux.p_cond - base.last_aux.p_cond
    f0 = base.y[base.plant.turbine.i_omega] / (2 * np.pi)
    f1 = sim.y[sim.plant.turbine.i_omega] / (2 * np.pi)
    print(f"\np_cond {base.last_aux.p_cond:.1f} -> {sim.last_aux.p_cond:.1f} Pa (d {dp:.1f}, "
          f"predicted {pred:.1f}); frequency {f0:.4f} -> {f1:.4f} Hz")
    assert dp == pytest.approx(pred, rel=1e-6)
    assert f1 < f0
    _audit_ok(sim, "condenser_fouling")


def test_fault_ramp_is_linear_with_exact_endpoint():
    sim = _sim([ScenarioEvent(10.0, "pump_degrade",
                              {"target": "cp1", "head_factor": 0.9, "ramp_s": 100.0})],
               max_t=200.0)
    vals = []
    while sim.t < 120.0:
        sim.step()
        vals.append((sim.t, sim.disc.head_factor["cp1"]))
    t, v = (np.array(c) for c in zip(*vals, strict=True))
    mid = v[np.argmin(np.abs(t - 60.0))]
    print(f"\ncp1 head_factor mid-ramp {mid:.4f} (linear 0.95); end {v[-1]!r}")
    assert np.all(np.diff(v) <= 0.0)
    assert v[-1] == 0.9
    assert mid == pytest.approx(0.95, abs=2e-3)
    assert not sim.fault_driver.ramps


def test_plant_fault_does_not_disturb_rng_draws():
    cfg = load_config()
    cfg["sensors"]["noise"] = {"drum_level": {"sigma": 0.003}}
    rec = []
    for ev in ([], [ScenarioEvent(5.0, "valve_degrade", {"target": "frv", "cv_factor": 0.7})]):
        sim = _sim(ev, cfg=cfg, max_t=60.0)
        z = []
        while sim.t < 60.0:
            sim.step()
            z.append(sim.sensors.last_draws.copy())
        rec.append(np.array(z))
    assert np.array_equal(rec[0], rec[1])


# --------------------------------------------------------------- validation

@pytest.mark.parametrize(("line", "msg"), [
    ("{t: 1, type: pump_degrade, target: fp9, head_factor: 0.9}", "target must be"),
    ("{t: 1, type: pump_degrade, target: fp1}", "missing"),
    ("{t: 1, type: valve_degrade, target: frv, cv_factor: 0}", "must be > 0"),
    ("{t: 1, type: firing_degrade, eta_factor: 0.9, ramp_s: -1}", "ramp_s"),
    ("{t: 1, type: actuator_stuck, target: drum}", "target must be"),
    ("{t: 1, type: actuator_slow, target: da_lcv, rate_factor: 0.5}", "target must be"),
])
def test_malformed_plant_fault_fails_at_load(tmp_path, line, msg):
    p = tmp_path / "bad.yaml"
    p.write_text(f"name: bad\ninit: {{load_mw: 60}}\nevents:\n  - {line}\nend: {{max_t: 10}}\n")
    with pytest.raises(ValueError, match=msg):
        load_scenario(p)
