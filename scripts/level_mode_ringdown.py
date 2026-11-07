#!/usr/bin/env python3
"""Ring-down of the slow drum-level mode under three-element feedwater control.

Diagnostic for the instability the M4 quiet-day run exposed (HANDOFF, 0.4.0
"known issue: AB + 3E slow level mode"). Noise-free: +6 MW stepped onto the
non-vital block at t = 300 s and held; TRUE drum level recorded at 1 Hz;
extrema of its 60 s moving average, relative to the last hour's mean.

Usage:
    python scripts/level_mode_ringdown.py [--drum two_state|astrom_bell]
        [--trim-kp KP] [--trim-ki KI] [--hours H]

Damping estimate: log decrement between same-sign extrema,
delta = ln|x_i / x_{i+2}|, zeta = delta / sqrt(4 pi^2 + delta^2). Only
extrema above 10 % of the largest deviation count, so the estimate isn't
fitted to the noise floor of a decayed response.
"""
from __future__ import annotations

import argparse

import numpy as np

from hotwell.plant import load_config
from hotwell.scenario import Scenario, ScenarioEvent
from hotwell.simulator import Simulator


def ringdown(drum: str = "astrom_bell", trim: dict | None = None,
             hours: float = 6.0) -> dict:
    cfg = load_config()
    cfg["drum"]["model"] = drum
    cfg["control"]["drum_level"]["three_element"] = True
    for k, v in (trim or {}).items():
        cfg["control"]["drum_level_3e"]["trim"][k] = v
    t_end = hours * 3600.0
    sc = Scenario("level_mode_ringdown", 42, 60.0, "islanded",
                  (ScenarioEvent(300.0, "set_load", {"target": "nonvital", "p0": 54.0e6}),),
                  t_end)
    sim = Simulator(cfg, scenario=sc)
    sim.initialize_steady_state(60.0)
    tt, lv, trim_out = [], [], []
    k = 0
    while sim.t < t_end - 0.5 * sim.dt:
        sim.step()
        k += 1
        if k % 20 == 0:
            tt.append(sim.t)
            lv.append(sim.last_aux.drum_level)
            trim_out.append(sim.control.fw_trim.output)
    tt, lv, trim_out = map(np.array, (tt, lv, trim_out))
    post = tt > 400.0
    x = lv[post] - np.mean(lv[tt > t_end - 3600.0])
    t = tt[post]
    xs = np.convolve(x, np.ones(61) / 61, mode="same")
    d = np.diff(xs)
    idx = np.where(np.sign(d[1:]) != np.sign(d[:-1]))[0] + 1
    floor = 0.1 * float(np.max(np.abs(xs)))
    ext = [(float(t[i]), float(xs[i])) for i in idx if abs(xs[i]) > floor]
    # keep alternating-sign extrema only (first of each run)
    alt: list[tuple[float, float]] = []
    for e in ext:
        if not alt or np.sign(e[1]) != np.sign(alt[-1][1]):
            alt.append(e)
    pairs = [(alt[i], alt[i + 2]) for i in range(len(alt) - 2)]
    periods = [b[0] - a[0] for a, b in pairs]
    decs = [float(np.log(abs(a[1] / b[1]))) for a, b in pairs]
    zetas = [dl / float(np.sqrt(4 * np.pi ** 2 + dl ** 2)) for dl in decs]
    return {"drum": drum, "trim": trim or {}, "extrema": alt, "periods": periods,
            "log_decrements": decs, "zetas": zetas,
            "std_after_1h_mm": float(np.std(lv[tt > 3600.0]) * 1e3),
            "max_dev_mm": float(np.max(np.abs(x)) * 1e3),
            "trim_range": (float(trim_out.min()), float(trim_out.max()))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drum", choices=("two_state", "astrom_bell"), default="astrom_bell")
    ap.add_argument("--trim-kp", type=float, default=None)
    ap.add_argument("--trim-ki", type=float, default=None)
    ap.add_argument("--hours", type=float, default=6.0)
    a = ap.parse_args()
    trim = {k: v for k, v in (("kp", a.trim_kp), ("ki", a.trim_ki)) if v is not None}
    r = ringdown(a.drum, trim, a.hours)
    print(f"drum {r['drum']}, 3E trim overrides {r['trim'] or 'none'}, {a.hours} h")
    print(f"level std after 1 h {r['std_after_1h_mm']:.1f} mm; max |dev| {r['max_dev_mm']:.1f} mm; "
          f"trim output {r['trim_range'][0]:.2f}..{r['trim_range'][1]:.2f} kg/s (limits +-25)")
    print("alternating extrema (t s, mm): "
          + ", ".join(f"({t:.0f}, {x * 1e3:+.1f})" for t, x in r["extrema"][:12]))
    print("periods (s): " + ", ".join(f"{p:.0f}" for p in r["periods"][:8]))
    print("log decrements: " + ", ".join(f"{v:+.3f}" for v in r["log_decrements"][:8]))
    print("zeta: " + ", ".join(f"{v:+.3f}" for v in r["zetas"][:8]))


if __name__ == "__main__":
    main()
