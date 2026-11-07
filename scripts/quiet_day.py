#!/usr/bin/env python3
"""Quiet-day acceptance run (0.4.0, plan M4): 24 h of normal operation, no fault.

Usage:
    python scripts/quiet_day.py [--fidelity two_state_1e|astrom_bell_3e]
                                [--seed N] [--until-h H] [--no-noise]
                                [--operator closed-loop|fixed]

Daily profile (gross MW, piecewise linear; every ramp is 60 min, so >= 20 min
each): 60 MW to 03:00, ramp to 36 MW by 04:00, hold to 10:00, ramp to 60 MW by
11:00, hold to 24:00. The profile moves the NON-VITAL block (vital held).

Operator (0.4.0 M6, default `--operator closed-loop`): the background operator
(hotwell.procedures.ProcedureRunner) runs NOP-03 (frequency trim) every 300 s,
a condensate pump swap at 06:00 and a feed pump swap at 18:00 (OPERATOR_SCHEDULE).
`--operator fixed` reproduces the M4 runs: `governor.load_ref_mw` = profile MW
every 10 s during ramps, open loop, and no swaps.

Noise preset (QUIET_DAY_SENSOR_NOISE / QUIET_DAY_LOAD_NOISE) is PROVISIONAL:
plausible orders of magnitude chosen for this acceptance run, not calibrated
instrument data. The bench repo owns item noise levels.

Pass criteria (plan M4): no protective trips, no rejected actions, |mass audit
drift| < 0.1 %. Alarms are enumerated, not failed on, so they can be explained.
Exit status 1 on failure.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field

import numpy as np

from hotwell.plant import load_config
from hotwell.procedures import ProcedureRunner, load_procedures
from hotwell.scenario import Scenario, ScenarioEvent
from hotwell.simulator import Simulator

FIDELITIES = {"two_state_1e": ("two_state", False), "astrom_bell_3e": ("astrom_bell", True)}

#: (hour, gross MW) breakpoints, piecewise linear.
PROFILE_H = [(0.0, 60.0), (3.0, 60.0), (4.0, 36.0), (10.0, 36.0), (11.0, 60.0), (24.0, 60.0)]
TRIM_PERIOD_S = 10.0   # --operator fixed only
#: (t [s], procedure id, params) for --operator closed-loop
OPERATOR_SCHEDULE = sorted(
    [(t, "NOP-03", {}) for t in range(300, 86400, 300)]
    + [(6 * 3600, "NOP-01", {"from": "cp1", "to": "cp2"}),
       (18 * 3600, "NOP-02", {"from": "fp1", "to": "fp2"})],
    key=lambda s: s[0])

# sigma in instrument units; tau [s] (0 = white). Provisional (see docstring).
QUIET_DAY_SENSOR_NOISE = {
    "drum_pressure": {"sigma": 1.5e4, "tau": 0.5},
    "chest_pressure": {"sigma": 1.5e4, "tau": 0.5},
    "drum_level": {"sigma": 3.0e-3, "tau": 1.0},
    "steam_flow": {"sigma": 0.3, "tau": 0.5},
    "feed_flow": {"sigma": 0.3, "tau": 0.5},
    "condensate_flow": {"sigma": 0.3, "tau": 0.5},
    "cond_pressure": {"sigma": 50.0, "tau": 0.0},
    "hotwell_level": {"sigma": 2.0e-3, "tau": 1.0},
    "da_level": {"sigma": 2.0e-3, "tau": 1.0},
    "da_pressure": {"sigma": 500.0, "tau": 0.0},
    "frequency": {"sigma": 0.005, "tau": 0.0},
    "mw_out": {"sigma": 5.0e4, "tau": 0.0},
    "cp1_current": {"sigma": 0.5, "tau": 0.0},
    "cp2_current": {"sigma": 0.5, "tau": 0.0},
    "fp1_current": {"sigma": 1.0, "tau": 0.0},
    "fp2_current": {"sigma": 1.0, "tau": 0.0},
    "fw_valve_pos": {"sigma": 0.002, "tau": 0.0},
    "throttle_pos": {"sigma": 0.002, "tau": 0.0},
    "firing_rate": {"sigma": 0.002, "tau": 0.0},
    "da_lcv_pos": {"sigma": 0.002, "tau": 0.0},
    "fp1_npsh_margin": {"sigma": 0.03, "tau": 0.0},
    "fp2_npsh_margin": {"sigma": 0.03, "tau": 0.0},
    # 0.4.0 M5b instruments
    "makeup_flow": {"sigma": 0.05, "tau": 0.0},
    "makeup_valve_pos": {"sigma": 0.002, "tau": 0.0},
    "cp1_npsh_margin": {"sigma": 0.03, "tau": 0.0},
    "cp2_npsh_margin": {"sigma": 0.03, "tau": 0.0},
}
QUIET_DAY_LOAD_NOISE = {
    "nonvital": {"sigma_w": 3.0e5, "tau": 120.0},
    "vital": {"sigma_w": 5.0e4, "tau": 300.0},
}
WATCH = ("frequency", "drum_level", "drum_pressure", "da_level", "hotwell_level",
         "cond_pressure", "fp1_npsh_margin", "mw_out", "makeup_flow")  # makeup: M5b G6


def profile_mw(t_s: float) -> float:
    h = t_s / 3600.0
    hs, ms = zip(*PROFILE_H, strict=True)
    return float(np.interp(h, hs, ms))


def build_config(fidelity: str, noise: bool) -> dict:
    model, three_element = FIDELITIES[fidelity]
    cfg = load_config()
    cfg["drum"]["model"] = model
    cfg["control"]["drum_level"]["three_element"] = three_element
    if noise:
        cfg["sensors"]["noise"] = QUIET_DAY_SENSOR_NOISE
        cfg["loads"]["noise"] = QUIET_DAY_LOAD_NOISE
    return cfg


def build_scenario(nv0: float, seed: int, max_t: float, fixed_trims: bool = False) -> Scenario:
    """Non-vital ramps per profile segment (+ the fixed load-reference schedule
    when fixed_trims). nv0 = the non-vital block's p0 after steady init at
    60 MW [W]."""
    events = []
    for (h0, m0), (h1, m1) in zip(PROFILE_H, PROFILE_H[1:], strict=False):
        if m1 == m0:
            continue
        t0, t1 = h0 * 3600.0, h1 * 3600.0
        events.append(ScenarioEvent(t0, "set_load", {
            "target": "nonvital", "p0": nv0 + (m1 - 60.0) * 1e6, "ramp_s": t1 - t0}))
        for t in (np.arange(t0 + TRIM_PERIOD_S, t1 + 0.5 * TRIM_PERIOD_S, TRIM_PERIOD_S)
                  if fixed_trims else ()):
            events.append(ScenarioEvent(float(t), "action", {
                "command": {"governor.load_ref_mw": round(profile_mw(float(t)), 6)}}))
    events.sort(key=lambda e: e.t)
    return Scenario(name="quiet_day", seed=seed, load_mw=60.0, mode="islanded",
                    events=tuple(events), max_t=max_t)


@dataclass
class QuietDayResult:
    fidelity: str
    seed: int
    t_end: float
    wall_s: float
    trips: dict
    first_out: list
    rejected: list
    alarm_events: list = field(default_factory=list)   # (t, id, state)
    extrema: dict = field(default_factory=dict)        # name -> (min, t_min, max, t_max)
    mass_drift_frac: float = 0.0
    relief_kg: float = 0.0
    state_hash: str = ""
    observation_hash: str = ""
    makeup_max_cmd: float = 0.0   # M5b G6: max makeup valve command over the day
    operator: str = "closed-loop"
    operator_log: list = field(default_factory=list)   # LogEntry list (closed-loop)

    @property
    def passed(self) -> bool:
        return (not any(self.trips.values()) and not self.first_out
                and not self.rejected and abs(self.mass_drift_frac) < 1e-3)


def run_quiet_day(fidelity: str = "two_state_1e", seed: int = 42, until_h: float = 24.0,
                  noise: bool = True, progress: bool = True,
                  operator: str = "closed-loop") -> QuietDayResult:
    cfg = build_config(fidelity, noise)
    probe = Simulator(cfg, seed=seed)
    probe.initialize_steady_state(60.0)
    nv0 = probe.plant.loads.nonvital.p0
    max_t = until_h * 3600.0
    fixed = operator == "fixed"
    sc = build_scenario(nv0, seed, max_t, fixed_trims=fixed)
    sim = Simulator(build_config(fidelity, noise), scenario=sc)
    sim.initialize_steady_state(60.0)
    ext = {k: [np.inf, 0.0, -np.inf, 0.0] for k in WATCH}
    prev: dict[str, str] = {}
    alarm_events = []
    wall0 = time.perf_counter()
    next_report = 0.0
    mu_max = 0.0
    runner = None if fixed else ProcedureRunner(load_procedures())
    pending = [] if fixed else [s for s in OPERATOR_SCHEDULE if s[0] < max_t]
    while sim.t < max_t - 0.5 * sim.dt:
        actions = None
        if runner is not None:
            while pending and pending[0][0] <= sim.t + 1e-9:
                _, pid, params = pending.pop(0)
                runner.start(pid, params, sim.t)
            actions = runner.tick(sim.last_obs, sim.loop_state(), sim.t) or None
        obs = sim.step(actions)
        mu_max = max(mu_max, sim.commands.mu_x)
        v = obs.values
        for k in WATCH:
            e = ext[k]
            if v[k] < e[0]:
                e[0], e[1] = v[k], sim.t
            if v[k] > e[2]:
                e[2], e[3] = v[k], sim.t
        cur = dict(obs.alarms)
        for aid, st in cur.items():
            if prev.get(aid) != st:
                alarm_events.append((round(sim.t, 2), aid, st))
        for aid in prev:
            if aid not in cur:
                alarm_events.append((round(sim.t, 2), aid, "clear"))
        prev = cur
        if obs.plant_dead:
            break
        if progress and sim.t >= next_report:
            print(f"[{fidelity}] t={sim.t / 3600:5.2f} h  profile {profile_mw(sim.t):5.1f} MW  "
                  f"mw_out {v['mw_out'] / 1e6:6.2f}  f {v['frequency']:6.2f} Hz  "
                  f"drum {v['drum_level'] * 1e3:+6.1f} mm {v['drum_pressure'] / 1e6:5.2f} MPa  "
                  f"alarms {len(cur)}  wall {time.perf_counter() - wall0:6.1f} s", flush=True)
            next_report += 3600.0
    rep = sim.audit()
    pumps_tripped = [p for p, m in sim.disc.pump_modes.items() if m == "tripped"]
    return QuietDayResult(
        fidelity=fidelity, seed=seed, t_end=sim.t, wall_s=time.perf_counter() - wall0,
        trips={"mft": sim.disc.mft, "turbine_trip": sim.disc.turbine_trip,
               "plant_dead": sim.disc.plant_dead, "pumps_tripped": bool(pumps_tripped)},
        first_out=list(sim.engine.first_out),
        rejected=[(r.t, r.action, r.reason) for r in sim.rejected],
        alarm_events=alarm_events,
        extrema={k: tuple(e) for k, e in ext.items()},
        mass_drift_frac=rep.mass_drift_frac,
        relief_kg=sim.audit_acc.relief_kg,
        state_hash=sim.state_history_hash, observation_hash=sim.observation_hash,
        makeup_max_cmd=mu_max, operator=operator,
        operator_log=list(runner.log) if runner is not None else [])


def print_result(r: QuietDayResult) -> None:
    print(f"\n=== quiet day: {r.fidelity}, seed {r.seed}: {'PASS' if r.passed else 'FAIL'} ===")
    print(f"simulated {r.t_end / 3600:.3f} h in {r.wall_s:.1f} s wall "
          f"({r.t_end / r.wall_s:.0f}x real time)")
    print(f"trips {r.trips}; first_out {r.first_out}; rejected actions {len(r.rejected)}")
    print(f"mass audit drift {r.mass_drift_frac * 100:+.5f} % (limit 0.1 %); "
          f"safety-valve relief {r.relief_kg:.1f} kg; makeup valve max cmd "
          f"{r.makeup_max_cmd}")
    print("sensed extrema (min @ t_h, max @ t_h):")
    for k, (lo, tlo, hi, thi) in r.extrema.items():
        print(f"  {k:16s} {lo:12.4f} @ {tlo / 3600:5.2f} h   {hi:12.4f} @ {thi / 3600:5.2f} h")
    acts = [e for e in r.alarm_events if e[2] == "active"]
    print(f"alarm transitions: {len(r.alarm_events)} ({len(acts)} activations)")
    for t, aid, st in r.alarm_events:
        print(f"  t={t / 3600:7.4f} h ({t:9.2f} s)  {aid:14s} {st}  "
              f"[profile {profile_mw(t):.1f} MW]")
    if r.operator_log:
        from collections import Counter
        ends = Counter((e.proc_id, e.outcome) for e in r.operator_log if e.step_id == "-")
        moves = sum(1 for e in r.operator_log if e.step_id == "trim" and e.outcome == "done"
                    and "after 0 moves" not in e.text)
        print(f"operator ({r.operator}): procedure outcomes {dict(sorted(ends.items()))}; "
              f"trims that needed moves {moves}")
        for e in r.operator_log:
            if e.proc_id in ("NOP-01", "NOP-02") or e.outcome not in ("started", "done",
                                                                      "completed"):
                print(f"  {e.t / 3600:7.4f} h  {e.proc_id} {e.step_id:15s} {e.outcome}")
    else:
        print(f"operator ({r.operator}): fixed load-reference schedule")
    print(f"state hash {r.state_hash}\nobs hash   {r.observation_hash}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fidelity", choices=sorted(FIDELITIES), default="two_state_1e")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--until-h", type=float, default=24.0)
    ap.add_argument("--no-noise", action="store_true")
    ap.add_argument("--operator", choices=("closed-loop", "fixed"), default="closed-loop")
    a = ap.parse_args()
    r = run_quiet_day(a.fidelity, a.seed, a.until_h, noise=not a.no_noise, operator=a.operator)
    print_result(r)
    sys.exit(0 if r.passed else 1)


if __name__ == "__main__":
    main()
