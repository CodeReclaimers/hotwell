#!/usr/bin/env python3
"""Regenerate the generated blocks of docs/manual/*.md from the contracts.

Usage:
    python scripts/gen_manual.py           rewrite every generated block in place
    python scripts/gen_manual.py --check   exit 1 (and list the files) if any
                                           block is stale; changes nothing

A block is the text between
    <!-- BEGIN GENERATED: <name> -->   and   <!-- END GENERATED: <name> -->
Everything outside the markers is hand-written prose and is never touched.
Sources: OBSERVATION_SPEC, ACTION_SCHEMA, the protection table, the procedure
YAML, the baseline config, and a live steady-state init at 60 MW (two_state +
1E, the baseline). tests/test_manual_sync.py runs the same renderer in memory
and fails on any difference.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from hotwell import steam_properties as sp
from hotwell import units as U
from hotwell.actions import ACTION_SCHEMA
from hotwell.plant import load_config
from hotwell.procedures import load_procedures
from hotwell.protection.tables import load_protection_table
from hotwell.sensors import OBSERVATION_SPEC
from hotwell.simulator import Simulator

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "docs" / "manual"
BLOCK = re.compile(r"(<!-- BEGIN GENERATED: (\w+) -->\n)(.*?)(<!-- END GENERATED: \2 -->)",
                   re.S)


def _table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def _g(x: float, sig: int = 4) -> str:
    return f"{x:.{sig}g}"


def _si(x: float, unit: str) -> str:
    """Readable SI: Pa -> kPa / MPa, W -> MW; otherwise the unit as given."""
    if unit == "Pa":
        return f"{_g(x / 1e6)} MPa" if abs(x) >= 1e6 else f"{_g(x / 1e3)} kPa"
    if unit == "W":
        return f"{_g(x / 1e6)} MW"
    return f"{_g(x)} {unit}".rstrip() if unit != "-" else _g(x)


# ------------------------------------------------------------------ blocks

def block_design_point() -> str:
    sim = Simulator(load_config(), seed=0)
    sim.initialize_steady_state(60.0)
    a, tb = sim.last_aux, sim.plant.turbine
    reg, y = sim.plant.registry, sim.y   # design point = TRUTH, not sensed values
    cfg = sim.cfg
    t_drum = sp.tsat(a.p_drum)
    rows = [
        ["Electrical output (gross, incl. station service)", f"{a.p_elec / 1e6:.3f} MW", ""],
        ["Station service (running pump motors)", f"{a.p_station_service / 1e3:.1f} kW", ""],
        ["Bus frequency", "60.00 Hz", ""],
        ["Drum pressure", f"{a.p_drum / 1e6:.3f} MPa", U.fmt("drum_pressure", a.p_drum)],
        ["Drum saturation temperature", f"{t_drum - 273.15:.1f} °C",
         U.DEGF_FROM_K.fmt(t_drum)],
        ["Main steam (turbine) flow", f"{a.m_throttle:.2f} kg/s",
         U.fmt("steam_flow", a.m_throttle)],
        ["Pegging steam to the deaerator", f"{a.m_peg:.2f} kg/s", U.KLB_HR.fmt(a.m_peg)],
        ["Feedwater flow", f"{a.m_fw:.2f} kg/s", U.fmt("feed_flow", a.m_fw)],
        ["Condensate flow", f"{a.m_cond:.2f} kg/s", U.fmt("condensate_flow", a.m_cond)],
        ["Makeup flow (normally zero)", f"{a.m_makeup:.2f} kg/s", U.fmt("makeup_flow", a.m_makeup)],
        ["Effective firing heat to fluid", f"{a.q_fire / 1e6:.1f} MW", ""],
        ["Condenser pressure", f"{a.p_cond / 1e3:.2f} kPa abs", U.fmt("cond_pressure", a.p_cond)],
        ["Condenser duty", f"{a.q_cond_duty / 1e6:.1f} MW", ""],
        ["Deaerator pressure (fixed)", f"{cfg['deaerator']['p_da'] / 1e3:.0f} kPa abs",
         U.fmt("da_pressure", cfg["deaerator"]["p_da"])],
        ["Turbine specific work / derived efficiency",
         f"{tb.specific_work(a.p_drum, a.p_cond) / 1e3:.1f} kJ/kg / {tb.eta_t:.4f}", ""],
        ["Throttle / feed reg valve / firing / DA LCV position",
         f"{y[reg.index('throttle.x')]:.4f} / {y[reg.index('fw_valve.x')]:.4f} / "
         f"{y[reg.index('firing.x')]:.4f} / {sim.commands.lcv_x:.4f}", ""],
        ["FP-1 NPSH margin", f"{a.feed_flow.margin[0]:.2f} m",
         U.fmt("fp1_npsh_margin", a.feed_flow.margin[0])],
        ["CP-1 NPSH margin", f"{a.cond_flow.margin[0]:.2f} m",
         U.fmt("cp1_npsh_margin", a.cond_flow.margin[0])],
        ["Total water inventory", f"{sim.audit().mass_total / 1e3:.2f} t", ""],
    ]
    return _table(["Quantity (rated, 60 MW)", "SI", "Customary"], rows)


def block_equipment() -> str:
    cfg = load_config()
    pc = cfg["pumps"]
    rows = []
    for cls, names in (("condensate", "CP-1, CP-2"), ("feed", "FP-1, FP-2")):
        p = pc[cls]
        h_svc = p["h0"] - p["k"] * p["q_rated"] ** 2
        rows.append([f"{cls.capitalize()} pumps ({names}), 2 x 100 %",
                     f"{p['q_rated']:.4f} m³/s service; shutoff head {p['h0']:.0f} m; "
                     f"{h_svc:.0f} m at service flow; motor {p['p_motor_rated'] / 1e3:.0f} kW; "
                     f"rated current {p['i_rated']:.0f} A"])
    t = cfg["turbine"]
    rows.append(["Turbine", f"throttle k_t {t['k_t']:.4e} kg/(s·Pa), rated position "
                 f"{t['x_rated']}, specific work {t['w_design'] / 1e3:.0f} kJ/kg at design, "
                 f"steam chest lag {t['tau_chest']} s"])
    r = cfg["rotor"]
    rows.append(["Generator / rotor", f"{r['s_rating'] / 1e6:.0f} MVA, H = {r['h_inertia']} s, "
                 f"{r['f0']:.0f} Hz, 2-pole (3600 rpm)"])
    c = cfg["condenser"]
    rows.append(["Condenser / hotwell", f"{c['p0'] / 1e3:.1f} kPa at zero exhaust + "
                 f"{c['p_load_slope'] / 1e3:.1f} kPa at rated exhaust; hotwell area "
                 f"{c['a_hotwell']} m², nominal level {c['hw_level_nominal']} m above bottom, "
                 f"{c['z_hw']} m above CP suction"])
    d = cfg["deaerator"]
    rows.append(["Deaerator", f"fixed {d['p_da'] / 1e3:.0f} kPa abs; area {d['area']} m², "
                 f"nominal level {d['level_nominal']} m, {d['z_da']} m above FP suction"])
    ts = cfg["drum"]["two_state"]
    rows.append(["Drum (two-state model)", f"{ts['v_total']} m³ total, {ts['v_liq_nwl']} m³ "
                 f"liquid at NWL, waterplane {ts['a_waterplane']} m²"])
    f = cfg["firing"]
    rows.append(["Firing", f"{f['q_fuel_max'] / 1e6:.0f} MW fuel at 100 %, combustion "
                 f"efficiency {f['eta_comb']}"])
    mu = cfg["makeup"]
    rows.append(["Makeup (CST → condenser)", f"tank at atmospheric pressure, "
                 f"{mu['t_cst'] - 273.15:.0f} °C, {mu['z_cst']} m above the condenser inlet; "
                 f"makeup valve passes {mu['capacity_design']:.0f} kg/s wide open at design "
                 f"vacuum (drawn in by the condenser vacuum); no reject path"])
    sv = cfg["safety_valve"]
    rows.append(["Drum safety valve", f"lifts {sv['p_open'] / 1e6:.2f} MPa "
                 f"({U.PSIG.fmt(sv['p_open'])}), reseats {sv['p_reseat'] / 1e6:.2f} MPa "
                 f"({U.PSIG.fmt(sv['p_reseat'])})"])
    for name, a in cfg["actuators"].items():
        rows.append([f"Actuator: {name}", f"lag {a['tau']} s, max slew {a['rate']} /s"])
    return _table(["Equipment", "Data (baseline config)"], rows)


def block_instruments() -> str:
    rows = []
    for s in OBSERVATION_SPEC:
        cu = U.INSTRUMENT_UNITS[s.name]
        lo, hi = cu.convert(s.lo), cu.convert(s.hi)
        rows.append([f"`{s.name}`", s.description, s.units,
                     f"{_si(s.lo, s.units)} … {_si(s.hi, s.units)}",
                     _si(s.resolution, s.units), f"{min(lo, hi):.{cu.decimals}f} … "
                     f"{max(lo, hi):.{cu.decimals}f} {cu.unit}"])
    return _table(["Instrument", "Measures", "SI unit", "SI range", "Resolution",
                   "Customary range"], rows)


def block_actions() -> str:
    rows = []
    for a in ACTION_SCHEMA:
        b = "" if a.lo is None else f"{_g(a.lo)} … {_g(a.hi)}"
        rows.append([f"`{a.key}`", a.kind, b, a.description, a.validity])
    return _table(["Action", "Type", "Bounds", "Effect", "Accepted when"], rows)


def block_loops() -> str:
    c = load_config()["control"]
    rows = [
        ["Governor", "sensed frequency", "throttle", "load reference (operator)",
         f"pure droop R = {c['governor']['droop']}", "always auto"],
        ["Drum level, single-element", "sensed drum level", "feed reg valve", "0 m (NWL)",
         f"kp {c['drum_level']['kp']}, ki {c['drum_level']['ki']}",
         "`loop.drum_level.mode`"],
        ["Drum level, three-element (option)", "drum level → flow trim; feed flow → valve",
         "feed reg valve", "0 m; demand = steam flow + trim",
         f"trim kp {c['drum_level_3e']['trim']['kp']}, ki {c['drum_level_3e']['trim']['ki']}; "
         f"flow kp {c['drum_level_3e']['flow']['kp']}, ki {c['drum_level_3e']['flow']['ki']}",
         "`loop.drum_level.mode`"],
        ["Drum pressure (boiler master)", "sensed drum pressure", "firing rate",
         f"{load_config()['design']['p_drum'] / 1e6:.1f} MPa",
         f"kp {c['drum_pressure']['kp']:.2e}, ki {c['drum_pressure']['ki']:.1e}",
         "`loop.drum_pressure.mode`"],
        ["Deaerator level", "sensed DA level", "DA LCV (direct)", "0 m (nominal)",
         f"kp {c['da_level']['kp']}, ki {c['da_level']['ki']}", "`loop.da_level.mode`"],
        ["Hotwell level (makeup)", "sensed hotwell level", "makeup valve (direct)",
         f"{c['hotwell_level']['setpoint']} m (below normal; closed in normal operation)",
         f"kp {c['hotwell_level']['kp']}, ki {c['hotwell_level']['ki']}, "
         f"{c['hotwell_level'].get('anti_windup', 'backcalc')} anti-windup",
         "`loop.hotwell_level.mode`"],
    ]
    return _table(["Loop", "Measures", "Moves", "Setpoint", "Tuning", "Auto/manual"], rows)


_ACTION_WORDS = {"alarm": "alarm only", "mft": "master fuel trip",
                 "turbine_trip": "turbine trip", "shed_nonvital": "shed non-vital load",
                 "safety_valve": "safety valve lifts"}


def _actions_text(c) -> str:
    """Protection actions in operator words (not the engine's identifiers)."""
    words = []
    for a in c.actions:
        if a == "trip_pump":
            words.append(f"trip {c.target.upper()[:2]}-{c.target[2:]}")
        else:
            words.append(_ACTION_WORDS[a])
    return ", ".join(words)


def _cond_text(c) -> str:
    sig = c.signal
    op = {"lt": "<", "gt": ">"}[c.op]
    unit = next(s.units for s in OBSERVATION_SPEC if s.name == sig)
    si = _si(c.setpoint, unit)
    cu = U.INSTRUMENT_UNITS[sig]
    cust = cu.fmt(c.setpoint)
    if cu.unit == unit:
        return f"`{sig}` {op} {si}"
    if cu.scale < 0:   # vacuum: the inequality flips in customary units
        op_c = {"<": ">", ">": "<"}[op]
        return f"`{sig}` {op} {si} ({op_c} {cust})"
    return f"`{sig}` {op} {si} ({op} {cust})"


def block_protection() -> str:
    t = load_protection_table()
    rows = []
    for c in t.conditions:
        acts = _actions_text(c)
        extra = f"; reseats {c.reseat / 1e6:.2f} MPa" if c.reseat else ""
        rows.append([f"`{c.id}`", " / ".join(c.label), _cond_text(c), f"{_g(c.delay)} s",
                     "yes" if c.latching else "no", acts + extra])
    return _table(["Id", "Window legend", "Condition (sensed)", "Delay", "Latching",
                   "Action"], rows)


def _cond_md(c: dict) -> str:
    if "signal" in c:
        op = {"lt": "<", "gt": ">", "le": "≤", "ge": "≥"}[c["op"]]
        return f"`{c['signal']}` {op} {c['value']}"
    return f"`{c['indication']}` is {'on' if c['eq'] else 'off'}"


def _step_md(n: str, s: dict) -> list[str]:
    out = [f"{n}. **{s.get('text', '')}**"]
    if "do" in s and s["do"]:
        acts = ", ".join(f"`{k}` = {str(v).lower() if isinstance(v, bool) else v}"
                         for k, v in s["do"].items())
        out.append(f"   - Action: {acts}")
    if s.get("wait_for"):
        out.append("   - Expect within " + f"{s['within']:g} s: "
                   + "; ".join(_cond_md(c) for c in s["wait_for"])
                   + (f". Otherwise go to *{s['on_timeout']['goto']}*."
                      if "on_timeout" in s else "."))
    if "hold" in s:
        out.append(f"   - Wait {s['hold']:g} s, then confirm: "
                   + ("; ".join(_cond_md(c) for c in s.get("check", [])) or "nothing")
                   + (f". Otherwise go to *{s['on_fail']['goto']}*." if "on_fail" in s else "."))
    if "trim" in s:
        t = s["trim"]
        out.append(f"   - Move `{t['key']}` by −{t['gain']:g} MW per Hz of error (at most "
                   f"{t['max_step']:g} MW per move, {t['settle_s']:g} s apart, up to "
                   f"{t['max_moves']} moves) until `{t['signal']}` is within "
                   f"{t['target']:g} ± {t['deadband']:g} Hz.")
    if s.get("ack_active"):
        out.append("   - `alarm.ack` each window that is flashing, one at a time.")
    return out


def block_procedures() -> str:
    out = []
    for pid, proc in sorted(load_procedures().items()):
        names = {k: f"<{k}>" for k in proc.params}
        d = proc.filled(names)
        out.append(f"### {pid} — {d['title']}\n")
        out.append(d.get("purpose", "").strip() + "\n")
        if proc.params:
            out.append("Parameters: " + ", ".join(f"`<{k}>` (e.g. `{v}`)"
                                                   for k, v in proc.params.items()) + ".\n")
        if d.get("applies_when"):
            out.append("**Applies when:** " + "; ".join(_cond_md(c) for c in d["applies_when"])
                       + ".\n")
        lines = []
        for i, s in enumerate(d["steps"], 1):
            lines += _step_md(str(i), s)
        out.append("**Steps**\n\n" + "\n".join(lines) + "\n")
        cont = d.get("contingencies") or {}
        if cont:
            cl = []
            for cid, s in cont.items():
                cl.append(f"- *{cid}*: {s.get('text', '')}"
                          + (" Action: " + ", ".join(f"`{k}`" for k in s.get("do", {}))
                             if s.get("do") else "")
                          + f" Outcome: {s.get('outcome', 'aborted')}.")
            out.append("**Contingencies**\n\n" + "\n".join(cl) + "\n")
    return "\n".join(out)


def block_arp(cid: str) -> str:
    """One-line generated header for an alarm-response section."""
    c = next((c for c in load_protection_table().conditions if c.id == cid), None)
    if c is None:
        raise KeyError(f"arp_{cid}: no such protection condition")
    acts = _actions_text(c)
    return (f"**Window:** {' / '.join(c.label)} · **Condition:** {_cond_text(c)} for "
            f"{_g(c.delay)} s · **Latching:** {'yes' if c.latching else 'no'} · "
            f"**Automatic action:** {acts}\n")


BLOCKS = {
    "design_point": block_design_point, "equipment": block_equipment,
    "instruments": block_instruments, "actions": block_actions, "loops": block_loops,
    "protection": block_protection, "procedures": block_procedures,
}


def render_file(text: str, cache: dict) -> str:
    def sub(m):
        name = m.group(2)
        if name not in cache:
            if name.startswith("arp_"):
                cache[name] = block_arp(name[len("arp_"):])
            elif name in BLOCKS:
                cache[name] = BLOCKS[name]()
            else:
                raise KeyError(f"unknown generated block {name!r}")
        return m.group(1) + cache[name] + m.group(4)
    return BLOCK.sub(sub, text)


def stale_files() -> dict[Path, str]:
    """{path: regenerated text} for every manual file whose blocks are stale."""
    cache: dict = {}
    out = {}
    for p in sorted(MANUAL.glob("*.md")):
        old = p.read_text()
        new = render_file(old, cache)
        if new != old:
            out[p] = new
    return out


def main() -> None:
    stale = stale_files()
    if "--check" in sys.argv:
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)}")
        sys.exit(1 if stale else 0)
    for p, text in stale.items():
        p.write_text(text)
        print(f"wrote {p.relative_to(ROOT)}")
    if not stale:
        print("manual up to date")


if __name__ == "__main__":
    main()
