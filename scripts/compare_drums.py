#!/usr/bin/env python3
"""M4 comparison: TwoStateDrum vs AstromBellDrum on the load_step scenario.

Produces one PNG (drum level + pressure, both models overlaid) showing the
shrink/swell inverse response the four-state model adds.

Usage: python scripts/compare_drums.py [--out out/]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from hotwell import data
from hotwell.plant import load_config
from hotwell.scenario import load_scenario
from hotwell.simulator import Simulator

C1, C2 = "#2a78d6", "#eb6834"  # validated categorical palette, fixed order
INK, INK_2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"

SCENARIO = data.builtin_scenarios()["load_step"]


def run_model(model: str):
    cfg = load_config()
    cfg["drum"]["model"] = model
    if model == "astrom_bell":
        # single-element level control is unstable against the AB drum's
        # cold-feed condensation coupling (see HANDOFF D18) — the M4 pairing
        # is AB + three-element feedwater.
        cfg["control"]["drum_level"]["three_element"] = True
    sim = Simulator(cfg, scenario=load_scenario(SCENARIO))
    sim.initialize_steady_state(sim.scenario.load_mw)
    sim.run()
    t, v = sim.historian.query(["drum_level", "drum_pressure"], -1.0,
                               sim.t + 1.0, max_points=8000)
    return t, v


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs = {"two-state (phase 1)": (run_model("two_state"), C1),
            "Astrom-Bell + 3-elem FW (M4)": (run_model("astrom_bell"), C2)}

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6.0), sharex=True)
    for label, ((t, v), c) in runs.items():
        a1.plot(t, v["drum_level"] * 1e3, color=c, lw=1.8, label=label)
        a2.plot(t, v["drum_pressure"] / 1e6, color=c, lw=1.8, label=label)
    for ax, ylab in ((a1, "drum level [mm]"), (a2, "drum pressure [MPa]")):
        ax.set_facecolor(SURFACE)
        ax.grid(True, alpha=0.25, linewidth=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylabel(ylab, color=INK)
        ax.tick_params(colors=INK_2)
        ax.legend(loc="best", fontsize=8, framealpha=0.9)
    a1.set_title("load_step (+6.83 MW at t=300 s) — drum model comparison\n"
                 "Astrom-Bell swells on the demand step; two-state is monotone",
                 color=INK, fontsize=11)
    a1.set_xlim(280, 600)
    a2.set_xlabel("t [s]", color=INK)
    fig.patch.set_facecolor(SURFACE)
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "drum_comparison_load_step.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
