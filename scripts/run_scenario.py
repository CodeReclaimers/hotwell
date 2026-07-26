#!/usr/bin/env python3
"""Run a scenario: print audit + first-out, optionally produce the standard
plot set and a CSV export.

Usage: python scripts/run_scenario.py <name|path.yaml> [--plots out/] [--csv FILE]

<name> resolves against the packaged canonical scenarios (load_step,
cp1_trip_recovered, cp1_trip_unrecovered); anything else is read as a path.

Plot set (PNG): drum level+pressure, frequency+MW, four flows, inventories,
valve positions, alarm/trip timeline strip. matplotlib is imported here only —
never by the hotwell package.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from hotwell import data
from hotwell.simulator import Simulator

# Validated categorical palette (dataviz reference, light mode, fixed order).
C1, C2, C3, C4, C5 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
STATUS_WARNING, STATUS_CRITICAL = "#fab219", "#d03b3b"
INK, INK_2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def resolve(name_or_path: str) -> data.Resource:
    """A packaged scenario name, else a filesystem path."""
    return data.builtin_scenarios().get(name_or_path, name_or_path)


def run(scenario_path: data.Resource):
    """Run to completion, collecting alarm transitions for the timeline."""
    sim = Simulator.from_scenario(scenario_path)
    transitions: list[tuple[float, str, str]] = []
    prev: dict[str, str] = {}
    while sim.t < sim.scenario.max_t:
        obs = sim.step()
        cur = dict(obs.alarms)
        for aid, state in cur.items():
            if prev.get(aid) != state:
                transitions.append((sim.t, aid, state))
        for aid in prev:
            if aid not in cur:
                transitions.append((sim.t, aid, "clear"))
        prev = cur
        if obs.plant_dead:
            break
    return sim, transitions


def print_report(sim: Simulator) -> None:
    rep = sim.audit()
    print(f"scenario '{sim.scenario.name}' ended at t={sim.t:.2f} s "
          f"(plant_dead={sim.disc.plant_dead})")
    print(f"mass audit:   drift {rep.mass_drift_frac * 100:+.4f}% of "
          f"{rep.mass_total / 1e3:.1f} t ({rep.mass_drift_frac_per_hour * 100:+.4f}%/h), "
          f"safety-valve relief {rep.mass_relief_integrated:.1f} kg")
    print(f"energy audit: residual {rep.energy_residual / 1e6:+.3f} MW "
          f"({rep.energy_residual_frac * 100:+.3f}% of firing)")
    if sim.engine.first_out:
        print("first-out:")
        for t, cid in sim.engine.first_out:
            print(f"  t={t:9.2f}  {cid}")
    else:
        print("first-out: (no trip-class events)")
    if sim.rejected:
        print("rejected actions:")
        for r in sim.rejected:
            print(f"  t={r.t:9.2f}  {r.action}  — {r.reason}")


def _style(ax, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, alpha=0.25, linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel(ylabel, color=INK)
    ax.tick_params(colors=INK_2)


def _refline(ax, y: float, label: str) -> None:
    ax.axhline(y, color=INK_2, linewidth=0.7, linestyle=":", alpha=0.6)
    ax.annotate(label, (1.0, y), xycoords=("axes fraction", "data"),
                fontsize=7, color=INK_2, va="bottom", ha="right")


def _end_labels(ax, t_end: float, entries: list[tuple[str, float]]) -> None:
    """Direct labels at line ends, pushed apart so they never collide."""
    lo, hi = ax.get_ylim()
    min_sep = 0.045 * (hi - lo)
    order = sorted(range(len(entries)), key=lambda i: entries[i][1])
    ys = [entries[i][1] for i in order]
    for k in range(1, len(ys)):
        if ys[k] - ys[k - 1] < min_sep:
            ys[k] = ys[k - 1] + min_sep
    for k, i in enumerate(order):
        ax.annotate(entries[i][0], (t_end, ys[k]), fontsize=8, color=INK,
                    xytext=(5, 0), textcoords="offset points", va="center",
                    annotation_clip=False)


def make_plots(sim: Simulator, transitions, out_dir: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    name = sim.scenario.name
    h = sim.historian
    sigs = ["drum_level", "drum_pressure", "frequency", "mw_out", "steam_flow",
            "feed_flow", "condensate_flow", "m_peg", "m_relief", "hotwell_level",
            "da_level", "fw_valve_pos", "throttle_pos", "firing_rate", "da_lcv_pos"]
    t, v = h.query(sigs, -1.0, sim.t + 1.0, max_points=8000)
    made: list[Path] = []

    def save(fig, stem: str) -> None:
        fig.patch.set_facecolor(SURFACE)
        fig.savefig(out_dir / f"{name}_{stem}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        made.append(out_dir / f"{name}_{stem}.png")

    # 1 — drum level + pressure (stacked, never twin axes)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True)
    a1.plot(t, v["drum_level"] * 1e3, color=C1, lw=1.8)
    for y, lab in ((-150, "LO"), (-300, "LOLO"), (150, "HI"), (300, "HIHI")):
        _refline(a1, y, lab)
    _style(a1, "drum level [mm]")
    a1.set_title(f"{name} — drum", color=INK)
    a2.plot(t, v["drum_pressure"] / 1e6, color=C2, lw=1.8)
    for y, lab in ((8.4, "HI"), (8.6, "SV open"), (8.3, "SV reseat"), (7.2, "LO")):
        _refline(a2, y, lab)
    _style(a2, "drum pressure [MPa]")
    a2.set_xlabel("t [s]", color=INK)
    save(fig, "drum")

    # 2 — frequency + electrical output
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 5.6), sharex=True)
    a1.plot(t, v["frequency"], color=C1, lw=1.8)
    for y, lab in ((59.5, "LO"), (58.8, "shed"), (57.0, "UF trip"), (60.5, "HI")):
        _refline(a1, y, lab)
    _style(a1, "frequency [Hz]")
    a1.set_title(f"{name} — electrical", color=INK)
    a2.plot(t, v["mw_out"] / 1e6, color=C2, lw=1.8)
    _style(a2, "electrical output [MW]")
    a2.set_xlabel("t [s]", color=INK)
    save(fig, "electrical")

    # 3 — the four flows (+ relief if it ever lifted)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    series = [("steam", v["steam_flow"], C1), ("feed", v["feed_flow"], C2),
              ("condensate", v["condensate_flow"], C3), ("pegging", v["m_peg"], C4)]
    if float(v["m_relief"].max()) > 0.0:
        series.append(("SV relief", v["m_relief"], C5))
    for lab, arr, c in series:
        ax.plot(t, arr, color=c, lw=1.8, label=lab)
    _style(ax, "flow [kg/s]")
    # direct end labels (contrast relief for the sub-3:1 palette slots)
    _end_labels(ax, t[-1], [(lab, float(arr[-1])) for lab, arr, _ in series])
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    ax.set_title(f"{name} — flows", color=INK)
    ax.set_xlabel("t [s]", color=INK)
    save(fig, "flows")

    # 4 — inventories (levels relative to nominal)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    inv = [("drum", v["drum_level"], C1), ("hotwell", v["hotwell_level"], C2),
           ("deaerator", v["da_level"], C3)]
    for lab, arr, c in inv:
        ax.plot(t, arr, color=c, lw=1.8, label=lab)
    _style(ax, "level rel. nominal [m]")
    _end_labels(ax, t[-1], [(lab, float(arr[-1])) for lab, arr, _ in inv])
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    ax.set_title(f"{name} — inventories", color=INK)
    ax.set_xlabel("t [s]", color=INK)
    save(fig, "inventories")

    # 5 — valve/actuator positions
    fig, ax = plt.subplots(figsize=(9, 4.2))
    acts = [("feed reg", "fw_valve_pos", C1), ("throttle", "throttle_pos", C2),
            ("firing", "firing_rate", C3), ("DA LCV", "da_lcv_pos", C4)]
    for lab, key, c in acts:
        ax.plot(t, v[key], color=c, lw=1.8, label=lab)
    _style(ax, "position [-]")
    ax.set_ylim(-0.05, 1.1)
    _end_labels(ax, t[-1], [(lab, float(v[key][-1])) for lab, key, _ in acts])
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    ax.set_title(f"{name} — actuators", color=INK)
    ax.set_xlabel("t [s]", color=INK)
    save(fig, "actuators")

    # 6 — alarm / trip timeline strip
    ids: list[str] = []
    for _, aid, _state in transitions:
        if aid not in ids:
            ids.append(aid)
    fig, ax = plt.subplots(figsize=(9, 0.5 + 0.34 * max(len(ids), 3)))
    spans: dict[str, float | None] = {}
    trip_ids = {cid for _, cid in sim.engine.first_out}
    for k, aid in enumerate(ids):
        color = STATUS_CRITICAL if any(aid in tid for tid in trip_ids) \
            else STATUS_WARNING
        start = None
        for tt, a2_, state in transitions:
            if a2_ != aid:
                continue
            if state in ("active", "acknowledged") and start is None:
                start = tt
            elif state == "clear" and start is not None:
                ax.barh(k, tt - start, left=start, height=0.55, color=color,
                        edgecolor=SURFACE)
                start = None
        if start is not None:
            ax.barh(k, sim.t - start, left=start, height=0.55, color=color,
                    edgecolor=SURFACE)
        spans[aid] = start
    labeled: list[tuple[float, str]] = []
    k_lab = 0
    for tt, cid in sim.engine.first_out:
        ax.plot([tt], [len(ids) + 0.35], marker="v", color=STATUS_CRITICAL,
                markersize=6, clip_on=False)
        if any(abs(tt - t2) < 1.0 and cid2 in cid for t2, cid2 in labeled):
            continue  # e.g. FP1_TRIP:FP1_SUCTION duplicates FP1_SUCTION
        ax.annotate(cid, (tt, len(ids) + 0.75 + 0.85 * (k_lab % 3)), fontsize=7,
                    color=INK, ha="center", va="bottom", annotation_clip=False)
        labeled.append((tt, cid))
        k_lab += 1
    ax.set_yticks(range(len(ids)), ids, fontsize=8, color=INK)
    ax.set_ylim(-0.6, len(ids) + 3.3)
    ax.set_xlim(0.0, sim.t * 1.02)
    _style(ax, "")
    ax.set_title(f"{name} — alarm/trip timeline (bars: alarm active; "
                 "markers: trip-class first-out)", color=INK, fontsize=10, pad=48)
    ax.set_xlabel("t [s]", color=INK)
    save(fig, "timeline")
    return made


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scenario")
    ap.add_argument("--plots", type=Path, default=None, metavar="DIR")
    ap.add_argument("--csv", type=Path, default=None, metavar="FILE")
    args = ap.parse_args()

    sim, transitions = run(resolve(args.scenario))
    print_report(sim)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        sim.historian.export_csv(args.csv)
        print(f"wrote {args.csv}")
    if args.plots:
        for p in make_plots(sim, transitions, args.plots):
            print(f"wrote {p}")


if __name__ == "__main__":
    main()
