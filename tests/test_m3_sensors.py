"""0.4.0 M3: sensor noise, new sensor fault kinds, the I2 draw contract,
and I5 TRUTH_SIGNALS."""
import time

import numpy as np
import pytest

from hotwell.historian import INDICATION_SIGNALS, TRUTH_SIGNALS
from hotwell.plant import load_config
from hotwell.rng import StreamBank
from hotwell.scenario import Scenario, ScenarioEvent, load_scenario
from hotwell.sensors import OBSERVATION_SPEC, SensorBank, SensorFault
from hotwell.simulator import DT, Simulator

NAMES = [s.name for s in OBSERVATION_SPEC]
I_DP = NAMES.index("drum_pressure")


def _truth(**over):
    """A constant truth vector, mid-range for every instrument."""
    t = {s.name: 0.5 * (s.lo + s.hi) for s in OBSERVATION_SPEC}
    t["drum_pressure"] = 8.0e6
    t.update(over)
    return t


def _bank(noise=None, seed=42):
    return SensorBank(noise, StreamBank(seed), DT)


def _noisy_cfg(**noise):
    cfg = load_config()
    cfg["sensors"]["noise"] = noise
    return cfg


# ------------------------------------------------------------ draw contract

def test_block_buffered_draws_equal_single_stream_sequence():
    """SensorBank refills 4096 draws at a time; across >1 block boundary the
    per-instrument draws must equal the stream's plain sequence."""
    bank = _bank()
    n = 2 * SensorBank.BLOCK + 123
    got = np.empty((len(NAMES), n))
    for k in range(n):
        bank.sample(k * DT, _truth())
        got[:, k] = bank.last_draws
    ref = StreamBank(42)
    worst = max(float(np.max(np.abs(got[i] - ref.stream(f"sensor.{nm}").normal(size=n))))
                for i, nm in enumerate(NAMES))
    print(f"\n{n} samples, 22 streams: max |bank draw - stream draw| = {worst}")
    assert worst == 0.0


def test_init_sample_is_noise_free_and_draws_nothing():
    quiet = Simulator(load_config(), seed=0)
    quiet.initialize_steady_state(60.0)
    noisy = Simulator(_noisy_cfg(drum_pressure={"sigma": 5e4}), seed=0)
    noisy.initialize_steady_state(60.0)
    print(f"\ninit drum_pressure quiet {quiet.last_obs.values['drum_pressure']:.0f} "
          f"noisy {noisy.last_obs.values['drum_pressure']:.0f}; "
          f"draws before first step: {noisy.sensors.last_draws}")
    assert noisy.last_obs.values == quiet.last_obs.values
    assert noisy.sensors.last_draws is None
    noisy.step()
    assert noisy.sensors.last_draws is not None


def _draw_record(sim, steps):
    rec = np.empty((steps, len(NAMES)))
    vals = np.empty((steps, len(NAMES)))
    for k in range(steps):
        obs = sim.step()
        rec[k] = sim.sensors.last_draws
        vals[k] = [obs.values[n] for n in NAMES]
    return rec, vals


@pytest.mark.parametrize("fault", [
    ScenarioEvent(5.0, "sensor_fault", {"target": "drum_level", "kind": "bias", "bias": 0.1}),
    ScenarioEvent(5.0, "sensor_fault", {"target": "feed_flow", "kind": "lag", "tau_s": 20.0}),
    ScenarioEvent(5.0, "trip_pump", {"target": "fp1", "reason": "overload"}),
], ids=["bias", "lag", "pump_trip"])
def test_i2_faulted_twin_shares_every_draw(fault):
    """Plan I2: a faulted run and its fault-free twin draw identical z
    sequences on EVERY instrument, the faulted one included, even when the
    fault (here, a feed-pump trip) changes the plant state drastically. The
    closed-loop sensed values legitimately differ; the raw draws must not."""
    noise = {n: {"sigma": s.resolution * 2.0, "tau": 1.0 if i % 2 else 0.0}
             for i, (n, s) in enumerate((s.name, s) for s in OBSERVATION_SPEC)}
    runs = []
    for events in ((), (fault,)):
        sc = Scenario(name="twin", seed=7, load_mw=60.0, mode="islanded",
                      events=events, max_t=200.0)
        sim = Simulator(_noisy_cfg(**noise), scenario=sc)
        sim.initialize_steady_state(60.0)
        runs.append(_draw_record(sim, 2000))
    (z0, v0), (z1, v1) = runs
    n_diff_vals = int(np.sum(np.any(v0 != v1, axis=0)))
    print(f"\n{fault.type}/{fault.params.get('kind', '')}: max |dz| "
          f"{float(np.max(np.abs(z0 - z1)))}; instruments whose sensed values "
          f"differ between twins: {n_diff_vals}/22")
    assert np.array_equal(z0, z1)
    assert n_diff_vals >= 1


# ------------------------------------------------------------- noise stats

def test_white_noise_sigma():
    sigma = 2.0e5  # Pa, 20 LSB, so quantization variance is negligible
    bank = _bank({"drum_pressure": {"sigma": sigma}})
    x = np.array([bank.sample(k * DT, _truth())["drum_pressure"] for k in range(10_000)])
    est = float(np.std(x - 8.0e6))
    r1 = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    print(f"\nwhite: sigma est {est:.0f} vs {sigma:.0f} ({est / sigma - 1:+.2%}); "
          f"lag-1 r {r1:+.4f}")
    assert est == pytest.approx(sigma, rel=0.03)
    assert abs(r1) < 0.04


def test_ar1_noise_autocorrelation_and_sigma():
    sigma, tau = 2.0e5, 2.0
    a = np.exp(-DT / tau)
    bank = _bank({"drum_pressure": {"sigma": sigma, "tau": tau}})
    x = np.array([bank.sample(k * DT, _truth())["drum_pressure"]
                  for k in range(100_000)]) - 8.0e6
    r1 = float(np.corrcoef(x[:-1], x[1:])[0, 1])
    est = float(np.std(x))
    print(f"\nAR(1) tau {tau} s: lag-1 r {r1:.5f} vs exp(-dt/tau) {a:.5f}; "
          f"sigma est {est:.0f} vs {sigma:.0f} ({est / sigma - 1:+.2%}, n_eff ~ "
          f"{100_000 * (1 - a) / (1 + a):.0f})")
    assert abs(r1 - a) < 0.01
    assert est == pytest.approx(sigma, rel=0.10)


def test_noise_increase_scales_sigma_and_stuck_masks_noise():
    sigma = 2.0e5
    bank = _bank({"drum_pressure": {"sigma": sigma}})
    bank.faults["drum_pressure"] = SensorFault(kind="noise_increase", factor=3.0)
    x = np.array([bank.sample(k * DT, _truth())["drum_pressure"] for k in range(10_000)])
    est = float(np.std(x - 8.0e6))
    bank.faults["drum_pressure"] = SensorFault(kind="stuck", t_start=0.0)
    held = {bank.sample(k * DT, _truth())["drum_pressure"] for k in range(500)}
    print(f"\nnoise_increase x3: sigma est {est:.0f} vs {3 * sigma:.0f}; "
          f"stuck over 500 noisy samples -> distinct values {held}")
    assert est == pytest.approx(3.0 * sigma, rel=0.03)
    assert len(held) == 1


# ---------------------------------------------------------- deterministic kinds

def test_drift_slope_and_cap():
    rate, cap = 1.0e-3, 0.05  # m/s, m
    bank = _bank()
    bank.faults["drum_level"] = SensorFault(kind="drift", rate=rate, max_bias=cap,
                                            t_start=10.0)
    ts = np.arange(0.0, 120.0, DT)
    y = np.array([bank.sample(t, _truth(drum_level=0.0))["drum_level"] for t in ts])
    ramp = (ts > 12.0) & (ts < 55.0)
    slope = float(np.polyfit(ts[ramp], y[ramp], 1)[0])
    print(f"\ndrift: fitted slope {slope:.6f} m/s vs {rate}; before start {y[ts < 10].max()}; "
          f"after cap {y[ts > 70].min():.3f}..{y[ts > 70].max():.3f} (cap {cap})")
    assert slope == pytest.approx(rate, rel=0.01)
    assert np.all(y[ts < 10.0] == 0.0)
    assert np.all(np.abs(y[ts > 70.0] - cap) < 1e-9)


def test_lag_step_response_reaches_63pct_at_tau():
    tau = 2.0
    bank = _bank()
    bank.faults["drum_pressure"] = SensorFault(kind="lag", tau_s=tau, t_start=0.0)
    bank.sample(0.0, _truth(drum_pressure=8.0e6))          # lag state starts at truth
    out = [bank.sample((k + 1) * DT, _truth(drum_pressure=9.0e6))["drum_pressure"]
           for k in range(400)]
    frac = (np.array(out) - 8.0e6) / 1.0e6
    k63 = int(np.argmax(frac >= 1 - np.exp(-1.0))) + 1        # steps after the step
    print(f"\nlag tau {tau} s: 63.2 % reached after {k63} steps (tau/dt = {tau / DT:.0f}); "
          f"first-step fraction {frac[0]:.4f} (1-exp(-dt/tau) = {1 - np.exp(-DT / tau):.4f})")
    assert abs(k63 - tau / DT) <= 1
    assert frac[-1] > 0.99


def test_lag_starts_without_a_jump_in_closed_loop():
    """The lag initialises at the current truth when the fault starts, so the
    sensed value doesn't step at fault onset."""
    sc = Scenario(name="lag_onset", seed=0, load_mw=60.0, mode="islanded",
                  events=(ScenarioEvent(2.0, "sensor_fault",
                                        {"target": "steam_flow", "kind": "lag",
                                         "tau_s": 30.0}),),
                  max_t=10.0)
    sim = Simulator(load_config(), scenario=sc)
    sim.initialize_steady_state(60.0)
    vals = [sim.step().values["steam_flow"] for _ in range(80)]
    jump = max(abs(b - a) for a, b in zip(vals, vals[1:], strict=False))
    print(f"\nsteam_flow around lag onset: {vals[38:42]}; max step-to-step change {jump}")
    assert jump <= 0.1 + 1e-9  # at most one LSB


# ------------------------------------------------------------ validation

@pytest.mark.parametrize(("line", "msg"), [
    ("{t: 1, type: sensor_fault, target: drum_level, kind: wobble}", "unknown kind"),
    ("{t: 1, type: sensor_fault, target: drum_level, kind: drift}", "missing"),
    ("{t: 1, type: sensor_fault, target: no_such, kind: stuck}", "unknown target"),
    ("{t: 1, type: sensor_fault, target: drum_level, kind: lag, tau_s: 0}", "tau_s > 0"),
    ("{t: 1, type: sensor_fault, target: drum_level, kind: noise_increase, factor: -1}",
     "factor >= 0"),
])
def test_malformed_sensor_fault_fails_at_load(tmp_path, line, msg):
    p = tmp_path / "bad.yaml"
    p.write_text(f"name: bad\ninit: {{load_mw: 60}}\nevents:\n  - {line}\nend: {{max_t: 10}}\n")
    with pytest.raises(ValueError, match=msg):
        load_scenario(p)


def test_noise_config_validation():
    with pytest.raises(ValueError, match="unknown instruments"):
        _bank({"no_such": {"sigma": 1.0}})
    with pytest.raises(ValueError, match=">= 0"):
        _bank({"drum_level": {"sigma": -1.0}})


# ------------------------------------------------------------ I5

def test_every_historian_signal_is_classified():
    """Plan I5: each historian signal is a sensed instrument, a truthful
    indication-derived signal, or explicitly TRUTH. A new historian signal
    fails here until it is classified, so a truth leak can't slip into a
    "what the operator saw" export by omission."""
    sim = Simulator(load_config(), seed=0)
    sim.initialize_steady_state(60.0)
    sigs = set(sim.historian.signals)
    inst = set(NAMES)
    unclassified = sigs - inst - INDICATION_SIGNALS - TRUTH_SIGNALS
    print(f"\nhistorian: {len(sigs)} signals = {len(sigs & inst)} instruments + "
          f"{len(sigs & INDICATION_SIGNALS)} indication-derived + "
          f"{len(sigs & TRUTH_SIGNALS)} truth {sorted(sigs & TRUTH_SIGNALS)}; "
          f"unclassified {sorted(unclassified)}")
    assert not unclassified
    assert not (inst & TRUTH_SIGNALS) and not (inst & INDICATION_SIGNALS)
    assert not (TRUTH_SIGNALS & INDICATION_SIGNALS)
    assert TRUTH_SIGNALS <= sigs


# ------------------------------------------------------------ cost

def test_noise_cost_is_recorded():
    """Informational: wall time for 10 min of sim with noise on every
    instrument (the 22 draws happen every step regardless). Loose bound only."""
    noise = {s.name: {"sigma": s.resolution, "tau": 0.0} for s in OBSERVATION_SPEC}
    walls = {}
    for label, cfg in (("no noise", load_config()), ("noise on all 22", _noisy_cfg(**noise))):
        sim = Simulator(cfg, seed=0)
        sim.initialize_steady_state(60.0)
        w0 = time.perf_counter()
        sim.run(600.0)
        walls[label] = time.perf_counter() - w0
    print("\n" + "; ".join(f"{k}: {v:.2f} s wall per 600 s sim" for k, v in walls.items()))
    assert walls["noise on all 22"] < 2.0 * walls["no noise"]
