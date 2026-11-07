"""0.4.0 M5b: hotwell makeup system, CP suction protection, tube_leak.
Gates G2-G5 of the approved spec (G1 = golden state hashes unchanged, in
test_golden_hashes.py; G6 = quiet days, slow; G7 = detectability sweep)."""
import numpy as np
import pytest

from hotwell.control.pid import PI, PIParams
from hotwell.plant import load_config
from hotwell.scenario import Scenario, ScenarioEvent, load_scenario
from hotwell.simulator import Simulator

FIDELITIES = {"two_state_1e": ("two_state", False), "astrom_bell_3e": ("astrom_bell", True)}


def _cfg(fidelity="two_state_1e"):
    model, te = FIDELITIES[fidelity]
    cfg = load_config()
    cfg["drum"]["model"] = model
    cfg["control"]["drum_level"]["three_element"] = te
    return cfg


def _sim(events=(), fidelity="two_state_1e", max_t=4000.0):
    sc = Scenario(name="m5b", seed=1, load_mw=60.0, mode="islanded",
                  events=tuple(sorted(events, key=lambda e: e.t)), max_t=max_t)
    sim = Simulator(_cfg(fidelity), scenario=sc)
    sim.initialize_steady_state(60.0)
    return sim


def _run(sim, until):
    while sim.t < until - 0.5 * sim.dt:
        sim.step()
        if sim.last_obs.plant_dead:
            break
    return sim


# ------------------------------------------------------------- anti-windup

def test_conditional_anti_windup_does_not_kick_a_closed_valve_open():
    """The G1 mechanism in isolation. A makeup-like PI (sp -0.15) sits closed
    while the level is far ABOVE setpoint, then the level returns to 0 (still
    above setpoint). Back-calculation tracking has absorbed -kp*e into the
    integrator and kicks the output open; conditional integration doesn't."""
    out = {}
    for aw in ("backcalc", "conditional"):
        pi = PI(PIParams(kp=13.0, ki=0.044, lo=0.0, hi=1.0, t_track=15.0, anti_windup=aw),
                -0.15)
        for _ in range(2000):            # 100 s at +0.5 m (hotwell high in a CP outage)
            pi.update(0.5, 0.05)
        out[aw] = (pi.integ, pi.update(0.0, 0.05))
    print(f"\nafter 100 s at +0.5 m then level 0: backcalc I {out['backcalc'][0]:.2f} -> "
          f"output {out['backcalc'][1]:.3f}; conditional I {out['conditional'][0]:.2f} -> "
          f"output {out['conditional'][1]:.3f}")
    assert out["backcalc"][1] > 0.5
    assert out["conditional"][1] == 0.0


# ------------------------------------------------------------- G2 leak steady state

@pytest.mark.slow   # 2 x 11000 s of sim (~100 s wall); run with pytest -m slow
@pytest.mark.parametrize("fidelity", sorted(FIDELITIES))
def test_g2_leak_steady_state_makeup_matches_leak(fidelity):
    """1 kg/s leak from t = 10 s; the makeup loop takes over at ~1150-1210 s.
    Gate on MEANS over t 6000-11000 s, not instantaneous values: the loop
    hunts on the 1 mm hotwell-level resolution (kp 13/m -> 0.13 kg/s per LSB),
    a quantization limit cycle like the governor's 0.01 Hz dither. The window
    starts ~2 AB slow-mode periods (~2490 s) after makeup takes over: at
    4000-6000 s the AB drum is still shedding inventory (-16.9 kg) and the
    makeup mean reads -1.18 %; over 6000-11000 s it is +0.14 % (measured
    2026-11-07). Spec deviation (G2 said "makeup = leak +- 1 %"); recorded in
    HANDOFF."""
    sim = _run(_sim([ScenarioEvent(10.0, "tube_leak", {"m_dot_design": 1.0})],
                    fidelity=fidelity, max_t=11000.0), 6000.0)
    rec = []
    k = 0
    while sim.t < 11000.0 - 0.5 * sim.dt:
        sim.step()
        k += 1
        if k % 20 == 0:
            a, v = sim.last_aux, sim.last_obs.values
            rec.append((a.m_leak, a.m_makeup, a.hw_level_rel,
                        v["feed_flow"] - v["steam_flow"] - a.m_peg))
    leak, mu, hw, imb = (np.array(c) for c in zip(*rec, strict=True))
    rep = sim.audit()
    print(f"\n{fidelity} (t 6000-11000 s): leak {leak.mean():.4f} kg/s; makeup mean "
          f"{mu.mean():.4f} ({mu.mean() / leak.mean() - 1:+.3%}), range {mu.min():.3f}.."
          f"{mu.max():.3f}, std {mu.std():.3f}; hotwell mean {hw.mean() * 1e3:+.2f} mm "
          f"(range {hw.min() * 1e3:+.1f}..{hw.max() * 1e3:+.1f}); sensed feed - steam - "
          f"truth pegging mean {imb.mean():.3f} kg/s"
          f"\n  audit: mass drift {rep.mass_drift_frac:.2e} (leak {rep.mass_leak_integrated:.1f}"
          f" kg, makeup {rep.mass_makeup_integrated:.1f} kg); energy residual "
          f"{rep.energy_residual_frac:.2e}; alarms {sim.last_obs.alarms}")
    assert mu.mean() == pytest.approx(leak.mean(), rel=0.01)
    assert hw.mean() == pytest.approx(-0.15, abs=0.005)
    assert np.all(np.abs(hw + 0.15) < 0.005)
    assert imb.mean() == pytest.approx(leak.mean(), abs=0.1)
    assert abs(rep.mass_drift_frac) < 1e-6
    assert abs(rep.energy_residual_frac) < 1e-3
    assert sim.last_obs.alarms == []


# ------------------------------------------------------------- G3 compound casualty

def test_g3_stuck_closed_makeup_plus_leak_trips_cp_on_suction():
    """Makeup stuck closed at t = 5 s, 1 kg/s leak from t = 10 s: the hotwell
    drains until CP-1 margin < 0.25 m for 5 s. Prediction: the margin falls 1:1
    with level (1.00 m at rated), so it loses 0.75 m x rhoA_hotwell of inventory
    at the leak rate (evaluated at the actual drum pressure)."""
    sim = _sim([ScenarioEvent(5.0, "actuator_stuck", {"target": "makeup_valve"}),
                ScenarioEvent(10.0, "tube_leak", {"m_dot_design": 1.0})], max_t=9000.0)
    rho_a = 992.0 * sim.cfg["condenser"]["a_hotwell"]
    seen = {}
    m0 = sim.last_obs.values["cp1_npsh_margin"]
    while sim.t < 9000.0 and not sim.engine.first_out:
        obs = sim.step()
        for aid, _ in obs.alarms:
            seen.setdefault(aid, round(sim.t, 1))
    leak = sim.last_aux.m_leak
    pred = 10.0 + (m0 - 0.25) * rho_a / leak + 5.0
    t_trip = sim.engine.first_out[0][0] if sim.engine.first_out else None
    _run(sim, sim.t + 120.0)
    print(f"\nCP-1 margin at t0 {m0:.2f} m; leak {leak:.4f} kg/s; predicted trip {pred:.0f} s, "
          f"measured {t_trip}; first alarm times {seen}; first_out "
          f"{[(round(t, 1), c) for t, c in sim.engine.first_out]}; makeup flow stayed "
          f"{sim.last_obs.values['makeup_flow']}")
    assert t_trip is not None
    assert sim.engine.first_out[0][1] == "CP1_SUCTION"
    assert seen["HOTWELL_LO"] < t_trip
    assert t_trip == pytest.approx(pred, rel=0.10)
    assert sim.disc.pump_modes["cp1"] == "tripped"


# ------------------------------------------------------------- G4 capacity

def test_g4_makeup_capacity_and_vacuum_dependence():
    sim = _sim(max_t=200.0)
    sim.step({"loop.hotwell_level.mode": "manual"})
    sim.step({"makeup_valve.manual_cmd": 1.0})
    sim.step()
    a = sim.last_aux
    pl = sim.plant
    cap = a.m_makeup
    # vacuum dependence: same open valve, +5 kPa of air ingress
    sim.disc.air_ingress = 5000.0
    sim.step()
    b = sim.last_aux
    head = pl.mu_p_atm + pl.mu_head
    pred = cap * ((head - b.p_cond) / (head - a.p_cond)) ** 0.5
    print(f"\nwide-open makeup {cap:.4f} kg/s at p_cond {a.p_cond:.1f} Pa (design 10.0); "
          f"with +5 kPa air ingress {b.m_makeup:.4f} kg/s at {b.p_cond:.1f} Pa (sqrt-law "
          f"prediction {pred:.4f})")
    assert cap == pytest.approx(10.0, rel=0.02)
    assert b.m_makeup < cap
    assert b.m_makeup == pytest.approx(pred, rel=1e-9)


def test_makeup_manual_command_rejected_in_auto():
    sim = _sim(max_t=10.0)
    sim.step({"makeup_valve.manual_cmd": 0.5})
    print(f"\nrejected: {[r.reason for r in sim.rejected]}")
    assert any("hotwell_level loop in auto" in r.reason for r in sim.rejected)


# ------------------------------------------------------------- G5 identity + validation

def test_g5_zero_tube_leak_is_bit_identical():
    a = _run(_sim(max_t=120.0), 120.0)
    b = _run(_sim([ScenarioEvent(10.0, "tube_leak", {"m_dot_design": 0.0, "ramp_s": 20.0})],
                  max_t=120.0), 120.0)
    assert a.state_history_hash == b.state_history_hash
    assert a.observation_hash == b.observation_hash


def test_leak_signature_hotwell_trends_down_before_makeup():
    """Before the hotwell reaches setpoint, the leak shows only as a falling
    hotwell (rate = leak / rhoA) and feed exceeding steam + pegging."""
    sim = _sim([ScenarioEvent(10.0, "tube_leak", {"m_dot_design": 0.3})], max_t=1500.0)
    _run(sim, 300.0)
    h1, t1 = sim.last_aux.hw_level_rel, sim.t
    _run(sim, 1200.0)
    h2, t2 = sim.last_aux.hw_level_rel, sim.t
    rate = (h2 - h1) / (t2 - t1) * 3600.0
    pred = -sim.last_aux.m_leak / (992.0 * sim.cfg["condenser"]["a_hotwell"]) * 3600.0
    print(f"\n0.3 kg/s leak: hotwell trend {rate:.4f} m/h (predicted {pred:.4f}); makeup "
          f"{sim.last_aux.m_makeup}")
    assert rate == pytest.approx(pred, rel=0.05)
    assert sim.last_aux.m_makeup == 0.0


@pytest.mark.parametrize(("line", "msg"), [
    ("{t: 1, type: tube_leak, m_dot_design: -1}", ">= 0"),
    ("{t: 1, type: tube_leak}", "missing"),
    ("{t: 1, type: actuator_slow, target: makeup_valve, rate_factor: 0.5}", "target must be"),
])
def test_malformed_m5b_events_fail_at_load(tmp_path, line, msg):
    p = tmp_path / "bad.yaml"
    p.write_text(f"name: bad\ninit: {{load_mw: 60}}\nevents:\n  - {line}\nend: {{max_t: 10}}\n")
    with pytest.raises(ValueError, match=msg):
        load_scenario(p)


def test_makeup_valve_fault_targets_accepted(tmp_path):
    p = tmp_path / "ok.yaml"
    p.write_text("name: ok\ninit: {load_mw: 60}\nevents:\n"
                 "  - {t: 1, type: actuator_stuck, target: makeup_valve}\n"
                 "  - {t: 2, type: valve_degrade, target: makeup_valve, cv_factor: 0.5}\n"
                 "end: {max_t: 10}\n")
    sc = load_scenario(p)
    assert [e.type for e in sc.events] == ["actuator_stuck", "valve_degrade"]
    assert np.isfinite(sc.max_t)
