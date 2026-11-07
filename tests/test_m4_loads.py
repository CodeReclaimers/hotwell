"""0.4.0 M4: load ramps and load process noise."""
import numpy as np
import pytest

from hotwell.components.loads import LoadBlock, LoadDriver, Loads
from hotwell.plant import load_config
from hotwell.rng import StreamBank
from hotwell.scenario import Scenario, ScenarioEvent, load_scenario
from hotwell.simulator import DT, Simulator


def _sim(events=(), noise=None, seed=3, max_t=2000.0):
    cfg = load_config()
    if noise is not None:
        cfg["loads"]["noise"] = noise
    sc = Scenario(name="m4", seed=seed, load_mw=60.0, mode="islanded",
                  events=tuple(events), max_t=max_t)
    sim = Simulator(cfg, scenario=sc)
    sim.initialize_steady_state(60.0)
    return sim


def _driver(noise, seed=42):
    loads = Loads(LoadBlock("vital", 12e6, 1.5), LoadBlock("nonvital", 47e6, 1.5))
    return loads, LoadDriver(loads, noise, StreamBank(seed), DT)


# ------------------------------------------------------------------ ramps

def test_ramp_is_linear_monotone_with_exact_endpoint():
    ramp_s, target = 600.0, 30.0e6
    sim = _sim([ScenarioEvent(10.0, "set_load",
                              {"target": "nonvital", "p0": target, "ramp_s": ramp_s})])
    p_start = sim.plant.loads.nonvital.p0
    trace = []
    while sim.t < 10.0 + ramp_s + 20.0:
        sim.step()
        trace.append((sim.t, sim.plant.loads.nonvital.p0))
    t, p = (np.array(c) for c in zip(*trace, strict=True))
    moving = (t > 10.0 + DT) & (t < 10.0 + ramp_s - DT)
    n = int(round(ramp_s / DT))
    mid = p[np.argmin(np.abs(t - (10.0 + ramp_s / 2)))]
    print(f"\nramp {p_start / 1e6:.4f} -> {target / 1e6:.1f} MW over {n} steps; "
          f"end {p[-1]!r}; mid {mid / 1e6:.4f} MW (linear midpoint "
          f"{(p_start + target) / 2e6:.4f}); first end-valued step t={t[p == target][0]:.2f}")
    assert np.all(np.diff(p) <= 0.0)
    assert np.all(np.diff(p[moving]) < 0.0)
    assert p[-1] == target                       # exact, not approximately
    assert int(np.sum(p != p_start) - np.sum(p == target)) == n - 1  # n-1 interior values
    assert mid == pytest.approx((p_start + target) / 2, rel=2e-3)
    assert not sim.load_driver.ramps


def test_new_set_load_replaces_active_ramp_from_current_value():
    sim = _sim([
        ScenarioEvent(10.0, "set_load", {"target": "nonvital", "p0": 20.0e6, "ramp_s": 1000.0}),
        ScenarioEvent(110.0, "set_load", {"target": "nonvital", "p0": 50.0e6, "ramp_s": 100.0}),
    ])
    while sim.t < 109.99:
        sim.step()
    p_mid = sim.plant.loads.nonvital.p0
    sim.step()
    p_next = sim.plant.loads.nonvital.p0
    while sim.t < 230.0:
        sim.step()
    print(f"\nat t=110 the first ramp is at {p_mid / 1e6:.4f} MW; next step "
          f"{p_next / 1e6:.4f} MW (second ramp starts from there); end "
          f"{sim.plant.loads.nonvital.p0 / 1e6:.4f} MW")
    assert p_mid < p_next < p_mid + 30.0e6 / 1000 * 1.5   # one small step up, no jump
    assert sim.plant.loads.nonvital.p0 == 50.0e6


def test_step_set_load_without_ramp_is_unchanged_behaviour():
    sim = _sim([ScenarioEvent(5.0, "set_load", {"target": "nonvital", "p0": 54.0e6})])
    while sim.t < 5.0:
        sim.step()
    assert sim.plant.loads.nonvital.p0 == 54.0e6
    assert not sim.load_driver.ramps


# ------------------------------------------------------------------ noise

def test_ou_load_noise_statistics():
    """tau = 10 s, 4e5 steps (~1000 correlation times after burn-in)."""
    sigma, tau = 3.0e5, 10.0
    loads, drv = _driver({"nonvital": {"sigma_w": sigma, "tau": tau}})
    n, burn = 400_000, int(5 * tau / DT)
    x = np.empty(n)
    for k in range(n):
        drv.advance()
        x[k] = loads.nonvital.p_dev
    x = x[burn:]
    a = np.exp(-DT / tau)
    lag = int(round(tau / DT))
    r1 = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    rtau = float(np.corrcoef(x[:-lag], x[lag:])[0, 1])
    est = float(np.std(x))
    print(f"\nOU tau {tau} s: sigma est {est:.0f} W vs {sigma:.0f} ({est / sigma - 1:+.2%}); "
          f"lag-1 r {r1:.5f} vs {a:.5f}; r(tau) {rtau:.4f} vs e^-1 {np.exp(-1):.4f}; "
          f"vital p_dev stays {loads.vital.p_dev}")
    assert est == pytest.approx(sigma, rel=0.10)
    assert abs(r1 - a) < 0.002
    assert abs(rtau - np.exp(-1.0)) < 0.08
    assert loads.vital.p_dev == 0.0


def test_load_noise_starts_from_zero_deviation():
    sigma, tau = 3.0e5, 120.0
    loads, drv = _driver({"nonvital": {"sigma_w": sigma, "tau": tau}})
    drv.advance()
    z = drv.last_draws["nonvital"]
    expect = sigma * np.sqrt(1 - np.exp(-2 * DT / tau)) * z
    print(f"\nfirst-step p_dev {loads.nonvital.p_dev:.2f} W = sigma*b*z "
          f"({expect:.2f}); a stationary start would be sigma*z = {sigma * z:.0f} W")
    assert loads.nonvital.p_dev == pytest.approx(expect, rel=1e-12)


@pytest.mark.parametrize("noise", [None, {"nonvital": {"sigma_w": 3e5, "tau": 60.0}}],
                         ids=["no_load_noise", "load_noise"])
def test_i2_load_draws_identical_across_fault_twins(noise):
    """Load streams draw once per step per block regardless of config or a
    plant upset (FP-1 trip -> bus eventually dead)."""
    rec = []
    for events in ((), (ScenarioEvent(5.0, "trip_pump", {"target": "fp1", "reason": "x"}),)):
        sim = _sim(events, noise=noise)
        z = []
        for _ in range(3000):
            sim.step()
            z.append((sim.load_driver.last_draws["vital"],
                      sim.load_driver.last_draws["nonvital"]))
        rec.append(np.array(z))
    print(f"\n{'with' if noise else 'without'} load noise: max |dz| between twins "
          f"{float(np.max(np.abs(rec[0] - rec[1])))}")
    assert np.array_equal(rec[0], rec[1])


def test_load_noise_moves_the_plant():
    """Closed-loop sanity: 0.3 MW OU (tau 30 s) on the non-vital block shows
    up as frequency wander. The quasi-static droop estimate (with load
    damping) is sigma_f = sigma_P / (P_r/R + k_pf P_blk) * f0 ~ 14 mHz. The
    plant responds MORE than that at this time scale: a load rise sags drum
    pressure, and P_m ~ p_drum, so frequency sags further until the 60 s-Ti
    pressure loop recovers. Measured 2026-11-07 (7200 s runs, seed 3): the
    ratio is 1.41 at tau = 30 s and 1.11 at tau = 300 s, with corr(p_drum,
    p_dev) = -0.65 / -0.34. Gate: the ratio is in (0.8, 2.0); no alarms."""
    sim = _sim(noise={"nonvital": {"sigma_w": 3.0e5, "tau": 30.0}}, max_t=1200.0)
    f, p = [], []
    while sim.t < 1200.0:
        sim.step()
        if sim.t > 300.0:
            f.append(sim.y[sim.plant.turbine.i_omega] / (2 * np.pi))
            p.append(sim.plant.loads.nonvital.p_dev)
    loads = sim.plant.loads
    p_blk = loads.vital.p0 + loads.nonvital.p0
    quasi = float(np.std(p)) / (60e6 / 0.05 + 1.5 * p_blk) * 60.0
    sf = float(np.std(f))
    print(f"\nfrequency std {sf * 1e3:.2f} mHz vs quasi-static {quasi * 1e3:.2f} mHz "
          f"(ratio {sf / quasi:.2f}); alarms {sim.last_obs.alarms}")
    assert 0.8 < sf / quasi < 2.0
    assert sim.last_obs.alarms == []


# ------------------------------------------------------------- validation

def test_load_noise_config_validation():
    with pytest.raises(ValueError, match="unknown blocks"):
        _driver({"nope": {"sigma_w": 1.0, "tau": 1.0}})
    with pytest.raises(ValueError, match="needs tau > 0"):
        _driver({"vital": {"sigma_w": 1.0, "tau": 0.0}})
    with pytest.raises(ValueError, match=">= 0"):
        _driver({"vital": {"sigma_w": -1.0, "tau": 1.0}})


@pytest.mark.parametrize(("line", "msg"), [
    ("{t: 1, type: set_load, target: industrial, p0: 1.0e+6}", "vital|nonvital"),
    ("{t: 1, type: set_load, target: nonvital, p0: 1.0e+6, ramp_s: -5}", "ramp_s >= 0"),
    ("{t: 1, type: set_load, target: nonvital, p0: -1.0}", "p0 >= 0"),
])
def test_malformed_set_load_fails_at_load(tmp_path, line, msg):
    p = tmp_path / "bad.yaml"
    p.write_text(f"name: bad\ninit: {{load_mw: 60}}\nevents:\n  - {line}\nend: {{max_t: 10}}\n")
    with pytest.raises(ValueError, match=msg):
        load_scenario(p)
