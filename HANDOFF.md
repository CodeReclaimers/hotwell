# HANDOFF — hotwell phase 1

## Status summary

**M3 complete — phase-1 finish line reached.** All acceptance tests pass (T1–T8,
T10–T12; T9 committed as skipped, gating the optional M4 drum). The three canonical
scenarios run, hit their timing targets, and produce the standard plot set. M4 not
started (requires explicit go-ahead per plan section 12).

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
| T2 steady state | **pass** | scaled ‖ydot‖_max = 2.1e-8 1/s at init (gate 1e-7); worst 600 s drift < 0.001% of span; zero alarms |
| T3 mass audit | **pass** | drift −0.000000% of 27.81 t inventory over 600 s |
| T4 energy audit | **pass** | residual −0.0000 MW = −0.0000% of firing |
| T5 determinism | **pass** | two `cp1_trip_recovered` runs, identical SHA-256 state-history hashes |
| T10 sensor fault | **pass** | +50 mm bias → true level driven low (underfeed); −350 mm bias → MFT on sensed LOLO with truth normal; first-out = DRUM_LVL_LOLO |
| T12 action validation | **pass** | running-pump start, manual-cmd-in-auto, unknown key, out-of-bounds all rejected-and-recorded with reasons; no raise |
| T6 droop | **pass** | Δf −0.2700 Hz vs analytic −0.2777 Hz on measured ΔP_e = 5.553 MW → 97.2% (gate ±5%); no alarms |
| T7 casualty (unrecovered) | **pass** | MFT via DRUM_LVL_LOLO; first protective trip FP1_SUCTION at +92.65 s (window 45–120 s); first-out = CP1_TRIP:overload |
| T8 casualty (recovered) | **pass** | zero trips; worst FP NPSH margin 2.30 m; levels re-established well inside +300 s (band by +78 s) |
| T9 inverse response | **skipped** | committed skip marker, gates the M4 drum |
| T11 performance | **pass** | 1 h simulated in 11.0 s wall (328× real time; budget 60 s) |

Suite: `31 passed, 1 skipped` (~23 s); ruff clean.

Property fit accuracy (max relative error vs source points, limit 0.5%): worst 0.051 %
(v_f(T)); all others ≤ 0.041 %. Full per-function report in the generated module
docstring.

## Achieved casualty timings vs targets

`cp1_trip_unrecovered` (CP-1 overload trip at t = 300 s), full annunciator sequence:

| t rel. CP-1 trip | Event | Target |
|---|---|---|
| +19.9 s | DRUM_P_HI alarm (pegging-steam demand lost, transient; clears ~+40 s) | — |
| +23.2 s | DA_LO alarm (DA draining) | — |
| +57.2 s | HOTWELL_HI alarm (condensate backing up) | — |
| **+92.7 s** | **FP1_SUCTION trip** (NPSH margin < 0.5 m sustained 5 s) | **45–120 s** ✓ |
| +98.0 s | SAFETY_VALVE lifts (feed lost at full steam draw; cycles ~5×) | believable (see D16) |
| +112.5 s | DRUM_LVL_LO alarm | — |
| **+127.4 s** | **DRUM_LVL_LOLO → MFT + turbine trip → bus dead → plant_dead** | required ✓ |

The DA buffer consumes ≈85 of the 92.7 s to first trip, as the plan intends.
First-out: CP1_TRIP:overload → FP1_SUCTION → FP1_TRIP:FP1_SUCTION → DRUM_LVL_LOLO.

`cp1_trip_recovered` (CP-2 started +12 s): worst FP NPSH margin 2.30 m (trip at
0.5 m — comfortable no-trip margin), zero alarms, all levels back in tight bands by
+78 s after the standby start (limit 300 s).

`load_step` (+6 MW on non-vital at t = 300 s): f settles 60.000 → 59.730 Hz; minimum
transient 59.41 Hz for < 2 s, so not even a transient FREQ_LO annunciation; drum
pressure dips to 7.67 MPa (alarm at 7.2); drum level max excursion −16 mm.

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
| Throttle / fw valve / firing / LCV | — | 0.850 / 0.553 / 0.801 / 0.600 | |
| NPSH margin FP1 / CP1 | — | 2.70 m / 1.00 m | |
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
  - Drum pressure PI kp=1.8e-7 1/Pa, ki=3e-9 (Ti=60 s): drum energy storage ≈534 J/Pa;
    kp gives ~12 s closed-loop TC on pressure (retuned in M3 — see below).
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
- **Pump curves**: shutoff = 1.25 × the pump's own rated head per plan. CP: 50 m
  shutoff / 40.2 m at service flow. FP: 1117 m shutoff / 962 m at service flow, with
  the pump's own rated point at 0.110 m³/s — 20% flow margin over the 0.0916 m³/s
  service point. The margin is load-bearing: the first FP sizing (1128/902 m, steeper
  K = 26934) starved the drum during the +10% load step with the FRV wide open
  (capacity ceiling ≈93.5 kg/s vs ≈95.8 needed) — drum level walked down ~0.15 mm/s
  with fw_valve.x saturated at 1.0. Found by probing load_step before writing T6.
- **FRV Cv = 0.1495** (x ≈ 0.55 at rated, ≈120 kg/s capacity wide-open with the flat
  pump); LCV Cv = 0.38295 (x ≈ 0.60 at rated).
- **Drum pressure PI retuned during M3** (kp 7e-8 → 1.8e-7 1/Pa, ~12 s closed-loop):
  at the original tuning, losing the 10.2 kg/s pegging draw on a CP trip drove drum
  pressure through the safety valve 21 s into the casualty. A boiler master that
  lifts safeties on a 12% demand loss is not believable; the tighter loop caps the
  excursion at 8.47 MPa (DRUM_P_HI alarm only, transient).

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
- **D11 — sensing runs immediately before the event layer.** Plan section 3.2 lists
  "event layer" (step 4) before "sensors sample" (step 5), but protection must consume
  sensed values (locked decision, section 1). Internally the sensing pipeline therefore
  runs once right after RK4 and feeds both the protection evaluation and the returned
  observation; the observable ordering (discrete transitions settle before the
  historian records) is preserved.
- **D12 — trip slams are instantaneous position jumps.** MFT sets firing.x = 0 and a
  turbine trip sets throttle.x = 0 directly in the event layer, bypassing the actuator
  lags — modeling the separate fuel-trip/stop valves real plants have. While the latch
  is in, the corresponding controller command is forced to 0.
- **D13 — `set_load` scenario event type added.** Section 9's event-type list has no way
  to express its own first canonical scenario (the +10% non-vital load step); `set_load`
  sets a load block's P0 demand. Minimal, deterministic extension.
- **D15 — T6 evaluated against measured ΔP_e, not the commanded step.** On an islanded
  bus with load frequency dependence (k_pf = 1.5), a commanded +6 MW block step settles
  to ΔP_e = 5.553 MW; the droop law ties frequency to actual power, so Δf = −R·ΔP_e/
  P_rated·f0 is the honest analytic (97.2% match). Against the commanded 6 MW the same
  run reads 90.0% — outside the 5% gate for reasons that are physics, not error.
- **D16 — post-feed-loss safety-valve lift accepted as believable.** ~5 s after the FP
  trips (full steam draw, zero feed), drum pressure spikes: feedwater is the boiler's
  heat sink, and holding 8 MPa with no feed needs firing to run BACK ~80 MW faster
  than the 12 s pressure loop can act. The SV cycles ~5× between 8.6/8.3 MPa until
  the LOLO MFT kills firing — textbook loss-of-feedwater behavior; relief mass is
  audited. Alternative rejected: adding a loss-of-feed MFT (not in the plan's
  protection table; would also shortcut the drum-level LOLO story the plan asks for).
- **D14 — trips.reset semantics.** Reset clears engine latches whose condition has
  cleared, then recomputes MFT/turbine-trip flags from remaining latches; the generator
  breaker recloses if the turbine trip cleared, and tripped pumps drop to `stopped`
  (restartable) unless a pump-trip latch remains. Scenario-injected pump trips carry no
  engine latch and always clear to `stopped` on reset. Not exercised by the canonical
  scenarios; unit-level behavior only in phase 1.
- **D10 — turbine trip = generator breaker opens = bus dead.** Single generator,
  islanded, no station-service alternative is modeled, so a turbine trip deenergizes
  both load blocks AND the pump motors (pumps trip on "bus_dead"). This is what makes
  MFT + turbine trip terminate a casualty in `plant_dead` (M2 wires the pump-trip
  cascade). Alternative rejected: keeping pumps energized after a turbine trip would
  require a station-service/battery model the plan excludes.

## Known issues / rough edges

- The steady-state root residual is ~2e-8 (scaled) after the M3 feed-pump resize vs
  ~5e-16 before — hybr stops within xtol at a slightly flatter point. Well inside the
  T2 gate (1e-7); cosmetic.
- CP NPSH margin at rated is 1.00 m (no protection entry exists for CP suction, per
  plan table). If a hotwell-draining casualty is added later, consider a CP_SUCTION
  table entry.
- After MFT + turbine trip the drum closure sits near 8.3–8.4 MPa with everything
  isolated (no heat loss modeled), so pressure stays high in the dead plant. Scenarios
  end on plant_dead, so nothing consumes this state in phase 1.
- Late-run `load_step` MW trace shows ±0.05 MW dither from quantized sensed frequency
  through the droop law — honest sensor-resolution limit cycling, visible only when
  zoomed.

## Questions for Alan

None blocking. Two judgment calls to ratify (both documented, neither changes
contracts): D5 (pegging steam; firing at rated is 199.6 MW, not the reference
table's ≈180 MW) and D15 (T6 evaluated against measured ΔP_e).

## Notes for the panel phase

- The observation contract is `hotwell.sensors.OBSERVATION_SPEC` (22 instruments,
  SI, with ranges/resolutions) plus `Observation.indications` (pump run/trip lights,
  MFT/turbine-trip/breaker/SV flags — honest in phase 1) and `Observation.alarms`
  (list of (id, clear|active|acknowledged) straight from the protection table ids).
- The action surface is `hotwell.actions.ACTION_SCHEMA`; every key carries bounds and
  a validity note. Rejections come back as recorded reasons — the panel can surface
  them verbatim as operator feedback.
- `data/protection.yaml` ids are the annunciator window list; the timeline strip in
  `run_scenario.py` is a preview of the annunciator history display.
- Historian `query(signals, t0, t1, max_points)` is strip-chart-shaped; 20 Hz for the
  trailing 10 min, 1 Hz beyond — matches a panel chart recorder well.
- Frequency instrument range is 50–70 Hz so the 110% overspeed setpoint (66 Hz) is
  observable — a 55–65 Hz gauge would have clamped below the trip point (found during
  design; keep in mind when drawing gauge faces).
