#!/usr/bin/env python3
"""Generate src/hotwell/steam_properties.py from typed-in standard steam-table points.

Provenance
----------
Source data are standard saturated-steam table values (pressure table and
temperature table) as published in Moran/Shapiro and Cengel/Boles engineering
thermodynamics texts; both are tabulations of the IAPWS formulation to the
precision shown. Values were typed in below. Internal energies are derived as
u = h - p*v rather than transcribed, to reduce transcription-error surface.

CoolProp is deliberately NOT used and is not a dependency at generation or
run time.

Fit strategy
------------
- Family A — saturation vs pressure, 3–12 MPa (drum range), evaluated in
  z = ln(p / 8 MPa): Tsat, h_f, h_g, v_f as degree-4 polynomials in z; v_g as
  exp(poly(z)) for uniform relative accuracy; u_f, u_g derived from the h and
  v fits (u = h - p*v).
- Family B — saturation pressure vs temperature, 30–150 degC (condenser/NPSH
  range): ln(psat) as a degree-4 polynomial in T [K]; the inverse Tsat(p) over
  the same range as a degree-4 polynomial in ln(p); saturated-liquid h_f(T)
  and v_f(T) as degree-3 polynomials in T [K].

Acceptance: max relative error against every source point must be <= 0.5%
(plan section 5.1); the achieved errors are written into the generated module
docstring and printed here.

Run:  python scripts/gen_steam_props.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

OUT_PATH = Path(__file__).resolve().parent.parent / "src" / "hotwell" / "steam_properties.py"

# --- Family A source points: saturation pressure table, 3–12 MPa -----------------
# p [MPa], Tsat [degC], v_f [m3/kg], v_g [m3/kg], h_f [kJ/kg], h_g [kJ/kg]
SAT_P_TABLE = [
    (3.0, 233.90, 0.001217, 0.06668, 1008.42, 2804.2),
    (3.5, 242.60, 0.001235, 0.05707, 1049.75, 2803.4),
    (4.0, 250.40, 0.001252, 0.04978, 1087.31, 2801.4),
    (4.5, 257.49, 0.001269, 0.04406, 1121.87, 2798.3),
    (5.0, 263.99, 0.001286, 0.03944, 1154.23, 2794.3),
    (6.0, 275.64, 0.001319, 0.03244, 1213.35, 2784.3),
    (7.0, 285.88, 0.001351, 0.02737, 1267.00, 2772.1),
    (8.0, 295.06, 0.001384, 0.02352, 1316.64, 2758.0),
    (9.0, 303.40, 0.001418, 0.02048, 1363.26, 2742.1),
    (10.0, 311.06, 0.001452, 0.018026, 1407.56, 2724.7),
    (11.0, 318.15, 0.001489, 0.015987, 1450.10, 2705.6),
    (12.0, 324.75, 0.001527, 0.014263, 1491.30, 2684.9),
]

# --- Family B source points: saturation temperature table, 30–150 degC -----------
# T [degC], psat [kPa]
PSAT_T_TABLE = [
    (30, 4.246), (35, 5.628), (40, 7.384), (45, 9.593), (50, 12.349),
    (55, 15.758), (60, 19.940), (65, 25.03), (70, 31.19), (75, 38.58),
    (80, 47.39), (85, 57.83), (90, 70.14), (95, 84.55), (100, 101.35),
    (105, 120.82), (110, 143.27), (115, 169.06), (120, 198.53), (125, 232.1),
    (130, 270.1), (135, 313.0), (140, 361.3), (145, 415.4), (150, 475.8),
]

# T [degC], h_f [kJ/kg]
HF_T_TABLE = [
    (30, 125.79), (35, 146.68), (40, 167.57), (45, 188.45), (50, 209.33),
    (55, 230.23), (60, 251.13), (65, 272.06), (70, 292.98), (75, 313.93),
    (80, 334.91), (85, 355.90), (90, 376.92), (95, 397.96), (100, 419.04),
    (105, 440.15), (110, 461.30), (115, 482.48), (120, 503.71), (125, 524.99),
    (130, 546.31), (135, 567.69), (140, 589.13), (145, 610.63), (150, 632.20),
]

# T [degC], v_f [m3/kg]
VF_T_TABLE = [
    (30, 0.001004), (40, 0.001008), (50, 0.001012), (60, 0.001017),
    (70, 0.001023), (80, 0.001029), (90, 0.001036), (100, 0.001044),
    (110, 0.001052), (120, 0.001060), (130, 0.001070), (140, 0.001080),
    (150, 0.001091),
]

P_REF = 8.0e6  # Pa — center of the drum-range log variable
T0_K = 273.15


def fit_report(name: str, coeffs: np.ndarray, xs: np.ndarray, ys: np.ndarray,
               transform=None) -> tuple[float, str]:
    """Max relative error of polynomial fit vs source points."""
    pred = np.polyval(coeffs, xs)
    if transform is not None:
        pred = transform(pred)
    rel = np.abs(pred - ys) / np.abs(ys)
    err = float(np.max(rel))
    return err, f"{name:12s} max rel err {err * 100:.4f}%"


def main() -> None:
    tbl = np.array(SAT_P_TABLE)
    p_pa = tbl[:, 0] * 1e6
    z = np.log(p_pa / P_REF)
    tsat_k = tbl[:, 1] + T0_K
    v_f = tbl[:, 2]
    v_g = tbl[:, 3]
    h_f = tbl[:, 4] * 1e3  # J/kg
    h_g = tbl[:, 5] * 1e3  # J/kg
    u_f = h_f - p_pa * v_f  # derived, J/kg
    u_g = h_g - p_pa * v_g  # derived, J/kg

    deg = 4
    c_tsat = np.polyfit(z, tsat_k, deg)
    c_hf = np.polyfit(z, h_f, deg)
    c_hg = np.polyfit(z, h_g, deg)
    c_vf = np.polyfit(z, v_f, deg)
    c_lnvg = np.polyfit(z, np.log(v_g), deg)
    c_uf = np.polyfit(z, u_f, deg)
    c_ug = np.polyfit(z, u_g, deg)

    reports = []
    errs = []
    for name, c, ys, tr in [
        ("tsat", c_tsat, tsat_k, None),
        ("h_f", c_hf, h_f, None),
        ("h_g", c_hg, h_g, None),
        ("v_f", c_vf, v_f, None),
        ("v_g(ln)", c_lnvg, v_g, np.exp),
        ("u_f", c_uf, u_f, None),
        ("u_g", c_ug, u_g, None),
    ]:
        e, r = fit_report(name, c, z, ys, tr)
        errs.append(e)
        reports.append(r)

    tb = np.array(PSAT_T_TABLE)
    t_k = tb[:, 0] + T0_K
    psat_pa = tb[:, 1] * 1e3
    c_lnpsat = np.polyfit(t_k, np.log(psat_pa), 4)
    e, r = fit_report("psat(ln)", c_lnpsat, t_k, psat_pa, np.exp)
    errs.append(e)
    reports.append(r)

    lnp = np.log(psat_pa)
    c_tsat_low = np.polyfit(lnp, t_k, 4)
    e, r = fit_report("tsat_lowp", c_tsat_low, lnp, t_k, None)
    errs.append(e)
    reports.append(r)

    hb = np.array(HF_T_TABLE)
    c_hf_t = np.polyfit(hb[:, 0] + T0_K, hb[:, 1] * 1e3, 3)
    e, r = fit_report("hf_T", c_hf_t, hb[:, 0] + T0_K, hb[:, 1] * 1e3, None)
    errs.append(e)
    reports.append(r)

    vb = np.array(VF_T_TABLE)
    c_vf_t = np.polyfit(vb[:, 0] + T0_K, vb[:, 1], 3)
    e, r = fit_report("vf_T", c_vf_t, vb[:, 0] + T0_K, vb[:, 1], None)
    errs.append(e)
    reports.append(r)

    report_text = "\n".join(reports)
    print(report_text)
    worst = max(errs)
    print(f"worst: {worst * 100:.4f}%  (limit 0.5%)")
    if worst > 0.005:
        print("FAIL: fit accuracy exceeds 0.5% limit", file=sys.stderr)
        sys.exit(1)

    def lit(coeffs: np.ndarray) -> str:
        body = "".join(f"    {c!r},\n" for c in coeffs.tolist())
        return "(\n" + body + ")"

    def dlit(coeffs: np.ndarray) -> str:
        return lit(np.polyder(coeffs))

    module = f'''"""Saturated steam properties as committed polynomial fits.

AUTO-GENERATED by scripts/gen_steam_props.py — DO NOT EDIT BY HAND.
Regenerate with:  python scripts/gen_steam_props.py

Provenance: standard saturated-steam table values (Moran/Shapiro, Cengel/Boles;
tabulations of the IAPWS formulation), typed into the generator script.
Internal energies derived as u = h - p*v from the tabulated h and v.

Validity ranges:
- pressure family (drum): 3–12 MPa
- temperature family (condenser/deaerator/NPSH): 30–150 degC
  (303.15–423.15 K; psat 4.2–476 kPa)

Units: SI throughout — p [Pa], T [K], h/u [J/kg], v [m3/kg], rho [kg/m3].

Accuracy vs source points (max relative error, limit 0.5%):
{report_text}
"""
from __future__ import annotations

from math import exp, log

P_REF = {P_REF!r}  # Pa, center of drum-range log variable z = ln(p/P_REF)

_TSAT = {lit(c_tsat)}
_HF = {lit(c_hf)}
_HG = {lit(c_hg)}
_VF = {lit(c_vf)}
_LNVG = {lit(c_lnvg)}
_UF = {lit(c_uf)}
_UG = {lit(c_ug)}
_D_TSAT = {dlit(c_tsat)}
_D_HF = {dlit(c_hf)}
_D_HG = {dlit(c_hg)}
_D_VF = {dlit(c_vf)}
_D_LNVG = {dlit(c_lnvg)}
_D_UF = {dlit(c_uf)}
_D_UG = {dlit(c_ug)}

_LNPSAT = {lit(c_lnpsat)}
_TSAT_LOW = {lit(c_tsat_low)}
_HF_T = {lit(c_hf_t)}
_VF_T = {lit(c_vf_t)}


def _horner(c: tuple, x: float) -> float:
    acc = 0.0
    for ci in c:
        acc = acc * x + ci
    return acc


# ----- Family A: saturation vs pressure, valid 3e6..12e6 Pa ---------------------

def tsat(p: float) -> float:
    """Saturation temperature [K] vs pressure [Pa] (3–12 MPa)."""
    return _horner(_TSAT, log(p / P_REF))


def h_f(p: float) -> float:
    """Sat. liquid enthalpy [J/kg] vs pressure [Pa] (3–12 MPa)."""
    return _horner(_HF, log(p / P_REF))


def h_g(p: float) -> float:
    """Sat. vapor enthalpy [J/kg] vs pressure [Pa] (3–12 MPa)."""
    return _horner(_HG, log(p / P_REF))


def v_f(p: float) -> float:
    """Sat. liquid specific volume [m3/kg] vs pressure [Pa] (3–12 MPa)."""
    return _horner(_VF, log(p / P_REF))


def v_g(p: float) -> float:
    """Sat. vapor specific volume [m3/kg] vs pressure [Pa] (3–12 MPa)."""
    return exp(_horner(_LNVG, log(p / P_REF)))


def u_f(p: float) -> float:
    """Sat. liquid internal energy [J/kg] vs pressure [Pa] (3–12 MPa)."""
    return _horner(_UF, log(p / P_REF))


def u_g(p: float) -> float:
    """Sat. vapor internal energy [J/kg] vs pressure [Pa] (3–12 MPa)."""
    return _horner(_UG, log(p / P_REF))


# d/dp derivatives (chain rule through z = ln(p/P_REF): d/dp = (d/dz)/p)

def dv_f_dp(p: float) -> float:
    """d(v_f)/dp [m3/kg/Pa] (3–12 MPa)."""
    return _horner(_D_VF, log(p / P_REF)) / p


def dv_g_dp(p: float) -> float:
    """d(v_g)/dp [m3/kg/Pa] (3–12 MPa)."""
    z = log(p / P_REF)
    return exp(_horner(_LNVG, z)) * _horner(_D_LNVG, z) / p


def du_f_dp(p: float) -> float:
    """d(u_f)/dp [J/kg/Pa] (3–12 MPa)."""
    return _horner(_D_UF, log(p / P_REF)) / p


def du_g_dp(p: float) -> float:
    """d(u_g)/dp [J/kg/Pa] (3–12 MPa)."""
    return _horner(_D_UG, log(p / P_REF)) / p


# ----- Family B: low-pressure saturation, valid 303.15..423.15 K ----------------

def psat(t: float) -> float:
    """Saturation pressure [Pa] vs temperature [K] (303.15–423.15 K)."""
    return exp(_horner(_LNPSAT, t))


def tsat_lowp(p: float) -> float:
    """Saturation temperature [K] vs pressure [Pa] (4.2–476 kPa)."""
    return _horner(_TSAT_LOW, log(p))


def hf_t(t: float) -> float:
    """Sat. liquid enthalpy [J/kg] vs temperature [K] (303.15–423.15 K)."""
    return _horner(_HF_T, t)


def rho_f_t(t: float) -> float:
    """Sat. liquid density [kg/m3] vs temperature [K] (303.15–423.15 K)."""
    return 1.0 / _horner(_VF_T, t)
'''
    OUT_PATH.write_text(module)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
