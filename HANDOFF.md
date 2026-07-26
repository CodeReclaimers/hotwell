# HANDOFF — hotwell phase 1

## Status summary

**M0 complete** (skeleton + steam properties + state registry). M1–M3 not started.

## How to run

```bash
uv venv .venv && uv pip install -e '.[dev]'
.venv/bin/python -m pytest            # all tests
.venv/bin/python -m ruff check .      # lint
.venv/bin/python scripts/gen_steam_props.py   # regenerate property fits
```

Note: the system Python's matplotlib is broken against numpy 2.x on this machine — always
use the project venv.

## Test results

| Test | Status | Evidence |
|---|---|---|
| T1 property anchors | **pass** | Tsat(8 MPa) = 295.06 degC, Tsat(0.15 MPa) = 111.37 degC, h_g(8 MPa) = 2758.1 kJ/kg; 12 passed in 0.04s |
| T2–T12 | not started | — |

Property fit accuracy (max relative error vs source points, limit 0.5%): worst 0.051 %
(v_f(T)); all others ≤ 0.041 %. Full per-function report in the generated module
docstring.

## Achieved casualty timings vs targets

Not yet — M3.

## Reference design point, achieved values

Not yet — M1 will record the closed steady-state balance sheet here.

## Parameter / tuning decisions and rationale

None yet.

## Decisions taken under ask-vs-decide

- **D1 — property source**: typed-in standard steam-table points (Moran/Shapiro,
  Cengel/Boles tabulations of IAPWS) rather than ad-hoc CoolProp at generation time —
  no extra tooling, provenance fully visible in `scripts/gen_steam_props.py`. Internal
  energies derived as u = h − p·v instead of transcribed (smaller transcription-error
  surface); a test asserts u/h/v consistency of the independent fits (< 5e-4).
- **D2 — two extra low-range fits beyond the plan's two families**: `hf_t(T)` and
  `rho_f_t(T)` (saturated liquid enthalpy/density, 30–150 degC), plus the inverse
  `tsat_lowp(p)`. Needed for condensate/deaerator enthalpies, pump densities and NPSH;
  the plan's two families alone cannot supply them. Same source table, same 0.5% gate.
- **D3 — temperatures in kelvin** throughout the API (plan lists K among SI units even
  though prose quotes degC). Tests convert at the boundary.
- **D4 — property fit derivative functions** (`dv_f_dp` etc.) emitted alongside the fits;
  the two-state drum closure Newton needs an analytic Jacobian. Verified against central
  finite differences (rel err < 1e-5) in tests.

## Known issues / rough edges

None yet.

## Questions for Alan

None blocking.

## Notes for the panel phase

Nothing yet — observation/action contracts land in M2.
