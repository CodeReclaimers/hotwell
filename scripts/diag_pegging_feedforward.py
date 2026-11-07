#!/usr/bin/env python3
"""Diagnostic (0.4.0 M4b): does pegging-steam feedforward damp the AB + 3E
slow drum-level mode? It does not; this script is the evidence for rejecting
that fix ("option 2").

Monkeypatches the three-element flow demand to
    steam_flow + PEG + trim
with the trim re-initialised to ~0 at equilibrium, then runs the standard
ring-down (scripts/level_mode_ringdown.py, OLD trim tuning kp 15 / ki 0.15, the
tuning the question was asked about). PEG modes:
  dynamic  TRUE pegging flow from the previous step (an idealised measurement)
  static   pegging frozen at its t = 0 value (a constant offset; linear theory
           says this cannot change the damping)
  none     unpatched baseline

Usage: python scripts/diag_pegging_feedforward.py dynamic|static|none
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import level_mode_ringdown as lm  # noqa: E402

from hotwell.control.loops import ControlSystem  # noqa: E402
from hotwell.simulator import Simulator  # noqa: E402

OLD_TRIM = {"kp": 15.0, "ki": 0.15}


def main() -> None:
    mode = sys.argv[1]
    assert mode in ("dynamic", "static", "none"), mode
    state: dict[str, float] = {}

    def fw_cmd(self, sensed, dt):
        m = self.drum_level.mode
        self.fw_trim.mode = m
        self.fw_flow.mode = m
        self.fw_flow.manual_cmd = self.drum_level.manual_cmd
        trim = self.fw_trim.update(sensed["drum_level"], dt)
        peg = state["peg"] if mode == "dynamic" else state["peg0"]
        self.fw_flow.sp = sensed["steam_flow"] + peg + trim
        u = self.fw_flow.update(sensed["feed_flow"], dt)
        self.drum_level.output = u
        return u

    orig_step, orig_init = Simulator.step, Simulator.initialize_steady_state

    def step(self, actions=None):
        state["peg"] = self.last_aux.m_peg
        return orig_step(self, actions)

    def init(self, load_mw):
        obs = orig_init(self, load_mw)
        state["peg0"] = self.last_aux.m_peg
        if mode != "none":
            self.control.fw_trim.initialize(0.0, self.last_aux.drum_level)
        return obs

    if mode != "none":
        ControlSystem._fw_cmd = fw_cmd
    Simulator.step = step
    Simulator.initialize_steady_state = init
    r = lm.ringdown("astrom_bell", OLD_TRIM, hours=6.0)
    print(f"[{mode}] max |dev| {r['max_dev_mm']:.1f} mm; trim {r['trim_range'][0]:.2f}.."
          f"{r['trim_range'][1]:.2f} kg/s")
    print(f"[{mode}] periods {[round(p) for p in r['periods'][:6]]} s; "
          f"zeta {[round(z, 3) for z in r['zetas'][:6]]}")


if __name__ == "__main__":
    main()
