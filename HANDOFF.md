# HANDOFF — hotwell phase 1

## Status summary

**M2 complete** (protection engine + YAML table, actions, scenarios, sensor faults,
historian, determinism; T5/T10/T12 pass). M3 (casualty tuning + plots) not started.

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
| T1 property anchors | **pass** | Tsat(8 MPa) = 295.06 degC, Tsat(0.15 MPa) = 111.37 degC, h_g(8 MPa) = 2758.1 kJ/kg |
| T2 steady state | **pass** | scaled ‖ydot‖_max = 4.8e-16 1/s at init; worst 600 s drift 0.0005% of span |
| T3 mass audit | **pass** | drift −0.000000% of 27.81 t inventory over 600 s |
| T4 energy audit | **pass** | residual −0.0000 MW = −0.0000% of firing |
| T5 determinism | **pass** | two `cp1_trip_recovered` runs, identical SHA-256 state-history hashes |
| T10 sensor fault | **pass** | +50 mm bias → true level driven low (underfeed); −350 mm bias → MFT on sensed LOLO with truth normal; first-out = DRUM_LVL_LOLO |
| T12 action validation | **pass** | running-pump start, manual-cmd-in-auto, unknown key, out-of-bounds all rejected-and-recorded with reasons; no raise |
| T6–T8, T11 | not started | — (M3) |
| T9 inverse response | **skipped** | committed skip marker, gates the M4 drum |

Suite: `27 passed in 4.53s`; ruff clean. Wall-clock pace ≈ 9 s per simulated hour
(T11 budget is 60 s — margin 6×). T2 now also asserts zero alarms over the 600 s hold.

Property fit accuracy (max relative error vs source points, limit 0.5%): worst 0.051 %
(v_f(T)); all others ≤ 0.041 %. Full per-function report in the generated module
docstring.

## Achieved casualty timings vs targets

Not yet — M3.

## Reference design point, achieved values

`scripts/steady_state.py` regenerates this table (60 MW commanded):

| Quantity | Plan | Achieved | Note |
|---|---|---|---|
| Electrical output | 60 MW | 60.000 MW | |
| Drum pressure | 8.0 MPa | 8.0000 MPa | Tsat 295.06 degC |
| Turbine steam flow | ≈77 kg/s | 76.923 kg/s | |
| Pegging (aux) steam | — | 10.198 kg/s | see decision D5 |
| Feedwater flow | — | 87.121 kg/s | = steam + pegging |
| Firing heat (effective) | ≈180 MW | **199.59 MW** | plan's table formula omits DA heating; see D5 |
| Condenser duty | — | 139.59 MW | 7.000 kPa at rated |
| Energy closure | <2% | 0.0000% | |
| Throttle / fw valve / firing / LCV | — | 0.850 / 0.608 / 0.801 / 0.579 | |
| NPSH margin FP1 / CP1 | — | 2.70 m / 1.84 m | |
| Total water inventory | — | 27.81 t | incl. 2 t piping holdup |

Sizing-rule compliance (achieved):
- DA working inventory (normal level 2.5 m to NPSH-trip level ≈0.08 m): ≈6.9 t ≈ **79 s**
  of rated feed flow (rule ≥60 s).
- Hotwell working inventory (nominal to ±0.5 m band edge): ≈4.0 t ≈ **52 s** of rated
  condensate flow (rule ≥45 s).
- Drum liquid, NWL to −300 mm (LOLO): 0.3 m × 16 m² × 722.6 kg/m³ ≈ 3.47 t ≈ **45 s** of
  rated steam flow with feed lost (rule 25–60 s).

## Parameter / tuning decisions and rationale

- **Control gains** (`configs/baseline.yaml`, `control:` section) — one line each:
  - Drum level PI kp=3.0, ki=0.05 (Ti=60 s): valve-to-level plant is an integrator
    (~0.013 (m/s)/valve-unit); gives ~20 s closed-loop TC, no oscillation at 20 Hz.
  - Drum pressure PI kp=7e-8 1/Pa, ki=1e-9 (Ti=70 s): drum energy storage ≈534 J/Pa;
    kp gives ~30 s closed-loop TC on pressure; slower than level loop by design.
  - DA level PI kp=1.5, ki=0.025: same integrator logic on the 3 m² DA waterplane.
  - Governor: pure droop R=0.05, no integrator (plan-mandated); x_cmd scaled by
    x_rated=0.85 so load_ref = P_rated at f0 commands exactly rated flow (see D6).
- **k_t = P_rated/(x_rated·w_spec·p_drum) = 1.131222e-5 kg/(s·Pa)** — makes droop law,
  rated flow, and rated power exactly consistent (no t=0 command jump).
- **Firing ceiling** q_fuel_max=280 MW, eta_comb=0.89 (249.2 MW effective): leaves
  headroom for the feed-loss transient (drum needs ~212 MW to hold pressure with no
  feedwater enthalpy credit).
- **FP NPSH_req deliberately flat** (a=9.8 m, b=59.6): with a saturated DA, available
  NPSH is purely static + level − friction, so the curve constant dominates; sized so
  DA drain-down crosses the 0.5 m trip margin ≈95 s after a condensate loss (target
  window 45–120 s), just before the tank runs dry.
- **Pump curves**: shutoff = 1.25 × rated head per plan; CP 50/40.2 m, FP 1128/902 m;
  Cv's sized for valve positions ≈0.6 at rated (control authority both directions).

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
- **D5 — DA pegging steam (energy-closure requirement).** The plan's reference table
  computes firing as ṁ_s·(h_g − h_fw) with ṁ_s = turbine flow, but heating condensate
  (163 kJ/kg at 7 kPa) to feedwater enthalpy (467 kJ/kg at 0.15 MPa saturation) needs
  ≈23.4 MW that the table does not source; without it the T4 energy audit fails by ~13%
  of firing. Standard practice (and the physical mechanism that holds a DA at pressure)
  is auxiliary/pegging steam from the drum: m_peg = m_cond·(h_fw − h_c)/(h_g − h_fw),
  computed algebraically at the DA inlet. Consequences: feed flow = turbine flow +
  pegging (87.1 kg/s), firing at rated = 199.6 MW (not ≈180), energy audit closes to
  ~1e-6. The reference table's 60 MW / 77 kg/s / 8 MPa / 7 kPa anchors are unchanged.
  Alternative rejected: declaring the DA heating as an unmodeled audit input — closes
  the books without physics and hides a real steam draw from the drum.
- **D6 — droop law scaled by x_rated.** The plan's droop law (x_cmd = load_ref/P_rated −
  (1/R)Δf/f0) reaches x=1.0 at rated load_ref, while k_t is calibrated for rated flow at
  x=0.85 — the two conflict. Resolved by scaling the per-unit power command onto the
  valve: x_cmd = x_rated·(load_ref/P_rated − (1/R)·Δf/f0). Effective droop gain is
  preserved exactly (dP_m/dδ = −P_rated/R), and rated load at f0 sits at exactly 60 Hz.
- **D7 — steady-state root formulation.** The three actuator rows of the derivative are
  degenerate at equilibrium (command := position), and the hotwell mass-balance row is
  linearly dependent with the DA's (both pin the same condensate flow). Replaced by
  loop-equilibrium conditions (drum p/level, DA level, ω = ω0) plus hotwell LEVEL =
  nominal. 14 unknowns (13 states + LCV position) / 14 residuals, scipy hybr, warm
  analytic guess; converges to ‖ydot‖ ~ 5e-16.
- **D8 — hotwell/DA thermal model**: both are fixed-temperature saturated reservoirs
  (Tsat at p_cond / p_da); no liquid energy states. Consistent with the plan's mass-only
  inventories (§4.1) and the fixed-p_da simplification.
- **D9 — chest holdup in the mass audit**: the chest lag stores exactly
  k_t·τ_ch·p_chest kg (≈31 kg at rated); counted in total inventory so the mass audit
  closes exactly, not just approximately.
- **D10 — turbine trip = generator breaker opens = bus dead.** Single generator,
  islanded, no station-service alternative is modeled, so a turbine trip deenergizes
  both load blocks AND the pump motors (pumps trip on "bus_dead"). This is what makes
  MFT + turbine trip terminate a casualty in `plant_dead` (M2 wires the pump-trip
  cascade). Alternative rejected: keeping pumps energized after a turbine trip would
  require a station-service/battery model the plan excludes.

## Known issues / rough edges

None yet.

## Questions for Alan

None blocking.

## Notes for the panel phase

Nothing yet — observation/action contracts land in M2.
