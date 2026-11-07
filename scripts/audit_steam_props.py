#!/usr/bin/env python3
"""Audit the typed steam-table points and the committed fits against IAPWS-97.

Verification only. Needs the third-party `iapws` package, which is NOT a
hotwell dependency (runtime or dev) and is never imported by the package or
by the generator. Install it into a throwaway venv:

    uv venv /tmp/oracle && uv pip install --python /tmp/oracle/bin/python iapws
    /tmp/oracle/bin/python scripts/audit_steam_props.py

Reports, for each typed table in scripts/gen_steam_props.py and for the
derived s_g, the worst relative error against the oracle; then the same for
the committed fits in src/hotwell/steam_properties.py over a dense grid of
each family's validity range. Exit status 1 if anything exceeds 0.5 %.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

try:
    from iapws import IAPWS97
except ImportError:
    sys.exit("audit_steam_props: needs `iapws` (not a hotwell dependency); see docstring")

import gen_steam_props as g  # noqa: E402
import numpy as np  # noqa: E402

from hotwell import steam_properties as sp  # noqa: E402

LIMIT = 0.005
worst_all = 0.0


def report(name: str, pairs) -> None:
    global worst_all
    errs = [(abs(v - ref) / abs(ref), x) for x, v, ref in pairs]
    e, x = max(errs)
    worst_all = max(worst_all, e)
    print(f"{name:28s} worst {e * 100:.4f}% at {x}")


def sat_p(p_mpa, q):
    return IAPWS97(P=p_mpa, x=q)


def sat_t(t_c, q):
    return IAPWS97(T=t_c + 273.15, x=q)


print(f"oracle: iapws IAPWS97; limit {LIMIT * 100:.1f}%\n-- typed tables --")
report("SAT_P h_f", [(p, hf, sat_p(p, 0).h) for p, _, _, _, hf, _ in g.SAT_P_TABLE])
report("SAT_P h_g", [(p, hg, sat_p(p, 1).h) for p, _, _, _, _, hg in g.SAT_P_TABLE])
report("SAT_P v_g", [(p, vg, sat_p(p, 1).v) for p, _, _, vg, _, _ in g.SAT_P_TABLE])
report("SF_P s_f", [(p, s, sat_p(p, 0).s) for p, s in g.SF_P_TABLE])
report("derived s_g = s_f + h_fg/T",
       [(p, sf + (hg - hf) / (ts + 273.15), sat_p(p, 1).s)
        for (p, ts, _, _, hf, hg), (_, sf) in zip(g.SAT_P_TABLE, g.SF_P_TABLE, strict=True)])
report("PSAT_T psat", [(t, ps, sat_t(t, 0).P * 1e3) for t, ps in g.PSAT_T_TABLE])
report("HF_T h_f", [(t, h, sat_t(t, 0).h) for t, h in g.HF_T_TABLE])
report("SF_T s_f", [(t, s, sat_t(t, 0).s) for t, s in g.SF_T_TABLE])
report("HG_T h_g", [(t, h, sat_t(t, 1).h) for t, h in g.HG_T_TABLE])

print("-- committed fits, dense grid --")
ps = np.linspace(3.0, 12.0, 91)
report("s_f(p)", [(p, sp.s_f(p * 1e6) / 1e3, sat_p(p, 0).s) for p in ps])
report("s_g(p)", [(p, sp.s_g(p * 1e6) / 1e3, sat_p(p, 1).s) for p in ps])
report("h_g(p)", [(p, sp.h_g(p * 1e6) / 1e3, sat_p(p, 1).h) for p in ps])
ts = np.linspace(30.0, 150.0, 121)
report("sf_t(T)", [(t, sp.sf_t(t + 273.15) / 1e3, sat_t(t, 0).s) for t in ts])
report("hg_t(T)", [(t, sp.hg_t(t + 273.15) / 1e3, sat_t(t, 1).h) for t in ts])
report("hf_t(T)", [(t, sp.hf_t(t + 273.15) / 1e3, sat_t(t, 0).h) for t in ts])
pc = np.linspace(4.5, 60.0, 112)  # kPa: condenser range incl. low-vacuum excursions
report("tsat_lowp(p)", [(p, sp.tsat_lowp(p * 1e3), sat_p(p / 1e3, 0).T) for p in pc])

print(f"\nworst overall {worst_all * 100:.4f}% (limit {LIMIT * 100:.1f}%)")
sys.exit(1 if worst_all > LIMIT else 0)
