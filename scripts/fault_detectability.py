#!/usr/bin/env python3
"""Rough detectability sweep for the M5 hidden physical faults (0.4.0, plan M5).

Usage: python scripts/fault_detectability.py [--fidelity two_state_1e|astrom_bell_3e]
                                             [--workers N]

Method (an OPTIMISTIC ORACLE BOUND, not the benchmark's labelling):
- Constant 60 MW, quiet-day sensor + load noise preset (scripts/quiet_day.py),
  seed 42, 1 h. Each fault is a step at t = 300 s.
- Twin comparison: the faulted run and the fault-free run share every noise
  draw (invariant I2), so their sensed difference is the fault's effect alone.
- "Detected" = some instrument's |faulted - fault-free| exceeds
  max(3 sigma_noise, 2 LSB) for 10 consecutive 1 Hz samples. Reported:
  the delay after onset and the first instrument to cross.
An observer without the twin must beat the noise without a counterfactual,
so real detectability is worse. The bench repo does rigorous labelling.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from hotwell.scenario import Scenario, ScenarioEvent
from hotwell.sensors import OBSERVATION_SPEC
from hotwell.simulator import Simulator

_spec = importlib.util.spec_from_file_location(
    "quiet_day", Path(__file__).resolve().parent / "quiet_day.py")
quiet_day = importlib.util.module_from_spec(_spec)
sys.modules["quiet_day"] = quiet_day
_spec.loader.exec_module(quiet_day)

T_ON, T_END, SEED = 300.0, 3600.0, 42
NAMES = [s.name for s in OBSERVATION_SPEC]
THRESH = np.array([max(3.0 * quiet_day.QUIET_DAY_SENSOR_NOISE.get(s.name, {}).get("sigma", 0.0),
                       2.0 * s.resolution) for s in OBSERVATION_SPEC])

SWEEP: list[tuple[str, dict, str, list[float]]] = [
    ("pump_degrade", {"target": "fp1"}, "head_factor", [0.995, 0.99, 0.98, 0.97]),
    ("pump_degrade", {"target": "cp1"}, "head_factor", [0.99, 0.98, 0.95, 0.90]),
    ("valve_degrade", {"target": "frv"}, "cv_factor", [0.99, 0.98, 0.95, 0.90]),
    ("valve_degrade", {"target": "lcv"}, "cv_factor", [0.99, 0.98, 0.95, 0.90]),
    ("firing_degrade", {}, "eta_factor", [0.998, 0.995, 0.99, 0.98]),
    ("condenser_fouling", {}, "slope_factor", [1.05, 1.1, 1.25, 1.5]),
    ("actuator_slow", {"target": "fw_valve"}, "rate_factor", [0.5, 0.2, 0.05]),
    ("actuator_slow", {"target": "throttle"}, "rate_factor", [0.5, 0.2, 0.05]),
    ("actuator_slow", {"target": "firing"}, "rate_factor", [0.5, 0.2, 0.05]),
    ("tube_leak", {}, "m_dot_design", [0.1, 0.3, 1.0, 3.0]),          # M5b G7
]
STUCK = ["fw_valve", "throttle", "firing", "da_lcv"]


def _record(fidelity: str, event: ScenarioEvent | None) -> np.ndarray:
    cfg = quiet_day.build_config(fidelity, noise=True)
    sc = Scenario("detect", SEED, 60.0, "islanded", () if event is None else (event,), T_END)
    sim = Simulator(cfg, scenario=sc)
    sim.initialize_steady_state(60.0)
    rows, k = [], 0
    while sim.t < T_END - 0.5 * sim.dt:
        obs = sim.step()
        k += 1
        if k % 20 == 0:
            rows.append([obs.values[n] for n in NAMES])
    return np.array(rows)


def _job(args):
    fidelity, etype, params = args
    return args, _record(fidelity, ScenarioEvent(T_ON, etype, params))


def detect(base: np.ndarray, run: np.ndarray) -> tuple[float | None, str | None]:
    over = np.abs(run - base) > THRESH            # [t, instrument]
    best = None
    for i in range(over.shape[1]):
        col = over[:, i]
        run_len = np.convolve(col.astype(int), np.ones(10, int), mode="valid")
        hits = np.where(run_len == 10)[0]
        if hits.size:
            t_det = float(hits[0] + 1)            # 1 Hz samples start at t = 1 s
            if best is None or t_det < best[0]:
                best = (t_det, NAMES[i])
    if best is None:
        return None, None
    return max(0.0, best[0] - T_ON), best[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fidelity", choices=sorted(quiet_day.FIDELITIES), default="two_state_1e")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    jobs = [(a.fidelity, et, {**tgt, pname: m}) for et, tgt, pname, mags in SWEEP for m in mags]
    jobs += [(a.fidelity, "actuator_stuck", {"target": t}) for t in STUCK]
    with ProcessPoolExecutor(a.workers) as ex:
        base_f = ex.submit(_record, a.fidelity, None)
        results = list(ex.map(_job, jobs))
        base = base_f.result()
    print(f"fault detectability, {a.fidelity}, seed {SEED}, onset t = {T_ON:.0f} s, window "
          f"{T_END - T_ON:.0f} s (oracle twin bound; see docstring)", flush=True)
    print(f"{'fault':40s} {'magnitude':>10s} {'delay':>9s}  first instrument")
    for (_, et, params), run in results:
        tgt = params.get("target", "")
        mag = next((v for k, v in params.items() if k != "target"), "")
        delay, inst = detect(base, run)
        d = f"{delay:7.0f} s" if delay is not None else "      n/d"
        print(f"{et + ' ' + tgt:40s} {mag!s:>10s} {d}  {inst or '-'}", flush=True)


if __name__ == "__main__":
    main()
