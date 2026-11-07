# HANDOFF — hotwell 0.4.0

Benchmark-readiness core release, 2026-11-07, tag `v0.4.0`, plan
`PLAN-0.4-benchmark-core.md` (approved; decisions Q1–Q5 in its §4). Public at
<https://github.com/CodeReclaimers/hotwell> (MIT), installed from GitHub tags only:
`pip install "hotwell @ git+https://github.com/CodeReclaimers/hotwell@v0.4.0"`.

This file is the current state. History lives elsewhere:
- `CHANGELOG.md` lists every change per milestone (M0–M7) and starts with upgrade notes.
- `progress-*.md` holds per-commit logs with verbatim evidence and rejected alternatives.
- Earlier HANDOFFs are in git: `git show v0.3.0:HANDOFF.md`, and the 0.4.0
  milestone-by-milestone diary at `git show 3e381c3:HANDOFF.md`.

## Status summary

All 0.4.0 milestones are complete: M0, M1, M2, M3, M4, M4b, M5, M5b, M6, M7.

- **One physics change (M2):** turbine work depends on drum and condenser pressure, and
  there is a low-vacuum trip. Every 0.3.0 trajectory, hash and session log stops
  reproducing.
- **One control retune (M4b):** the AB drum + three-element level trim. AB + 3E
  hashes changed again; two_state + 1E did not.
- **Everything else is hash-neutral at defaults:**
  - named rng streams;
  - sensor noise and sensor fault kinds;
  - load ramps and load noise;
  - hidden plant faults;
  - makeup system;
  - procedures and the background operator;
  - action recorder;
  - manual.

  M5b grew the observation contract: 4 instruments appended, so the observation
  goldens were re-pinned while the state goldens stayed unchanged.

Consumers:
- **hotwell-panel** is still pinned to `v0.3.0` (GitHub tag) and has not been migrated.
  The list is under "Notes for the panel phase".
- **hotwell-bench** (private, not created on GitHub) has a draft plan,
  `../hotwell-bench/PLAN-bench-0.1.md`, awaiting answers to B-Q1…B-Q8.

## How to run

```bash
uv venv .venv && uv pip install -e '.[dev]'
.venv/bin/python -m pytest                 # default gate (excludes the slow set)
.venv/bin/python -m pytest -m slow -s      # 24-h quiet days, ring-downs, M5b G2
.venv/bin/python -m ruff check .
.venv/bin/python scripts/gen_manual.py --check   # manual's generated blocks are current
```

| Script | Produces |
|---|---|
| `scripts/steady_state.py` | design-point table + turbine sensitivities |
| `scripts/run_scenario.py <name> --events [--fidelity two_state_1e\|astrom_bell_3e] [--csv] [--plots DIR]` | casualty timelines, audits |
| `scripts/golden_hashes.py [SRC]` | the six golden runs, computed independently |
| `scripts/quiet_day.py [--fidelity …] [--operator closed-loop\|fixed] [--seed N]` | 24-h acceptance day |
| `scripts/fault_detectability.py [--fidelity …] [--workers N]` | oracle-twin detectability sweep |
| `scripts/level_mode_ringdown.py` | AB + 3E slow level-mode ring-down (M4b) |
| `scripts/gen_manual.py [--check]` | manual GENERATED blocks |
| `scripts/gen_steam_props.py`, `scripts/audit_steam_props.py` | property fits; IAPWS-97 audit (optional `iapws`) |

Use the project venv. The system Python's matplotlib is broken against numpy 2.x on
this machine.

## Test results

Release run, 2026-11-07, on `release-0.4` with the version bump applied:

- Default gate: `182 passed, 6 deselected in 181.83s (0:03:01)`.
- Slow set (`pytest -m slow`): `6 passed, 182 deselected in 1094.28s (0:18:14)`.
  AB ring-down ζ 0.4386, late/first 0.014; two_state + 3E ring-down ζ 0.4840, late/first 0.017.
- ruff clean; `gen_manual.py --check` exit 0.

Evidence below is the tests' own printout (`pytest -s`) from that run unless noted.

| Test | Status | Evidence (0.4.0) |
|---|---|---|
| T1 property anchors | pass | Tsat(8 MPa) 295.06 °C, Tsat(0.15 MPa) 111.37 °C, h_g(8 MPa) 2758.1 kJ/kg |
| T2 steady state | pass | scaled ‖ẏ‖_max 2.910e-16 1/s at init. Worst 600 s drift 0.0283 % of span (`drum.U`; gate 1 %). See Known issues: 0.0000 % at 0.2.0, 0.0266 % at 0.3.0 |
| T3 mass audit | pass | −0.000000 % of 27.81 t over 600 s |
| T4 energy audit | pass | residual −0.0023 MW = −0.0012 % of firing |
| T5 determinism | pass | six golden runs reproduce state + observation hashes and step counts (`tests/test_golden_hashes.py`) |
| T6 droop | pass | ΔP_e 6.362 MW; Δf −0.3200 Hz vs analytic −0.3181 Hz → 100.6 % (gate ±5 %) |
| T7 casualty (unrecovered) | pass | FP1_SUCTION at +92.90 s (window 45–120 s); MFT via DRUM_LVL_LOLO; first-out CP1_TRIP:overload |
| T8 casualty (recovered) | pass | zero trips; levels at +300 s: drum +1.0 mm, DA +0.002 m, HW −0.003 m |
| T9 inverse response | pass | AB swell +6.1 mm on the load step; two_state −0.0 mm (monotone) |
| T10 sensor fault | pass | bias → underfeed; −350 mm bias → MFT on sensed LOLO with truth normal |
| T11 performance | pass | 1 h simulated in 15.9 s wall (227× real time; budget 60 s) |
| T12 action validation | pass | rejections recorded with reasons, no raise |

0.4.0 gates (all in the default gate unless marked slow):
- golden hashes (M0);
- rng stream pins plus the numpy-version gate (M1);
- turbine/Clapeyron consistency and COND_P_HIHI (M2);
- sensor pipeline statistics and I2 through a feed-pump trip (M3);
- load ramps, load noise and the droop ratio (M4);
- quiet days and the AB/two_state ring-downs (M4/M4b, slow);
- fault signatures, audit closure and zero-magnitude identity (M5);
- makeup gates G1–G7 (M5b; G2 slow);
- procedures, runner and recorder replay identity (M6);
- manual sync, seven checks (M7);
- `__version__` equals the installed metadata (release).

## Achieved casualty timings vs targets

`scripts/run_scenario.py cp1_trip_unrecovered --events --fidelity <f>` (CP-1 overload
trip at t = 300 s). First activation, seconds after the trip:

| Event | two_state + 1E | AB + 3E | Target |
|---|---|---|---|
| DRUM_P_HI (pegging demand lost; clears) | +19.30 | +90.45 | — |
| DA_LO | +23.15 | +21.85 | — |
| HOTWELL_HI | +57.35 | +57.20 | — |
| **FP1_SUCTION trip** | **+92.90** | **+78.20** | **45–120 s** ✓ |
| DRUM_LVL_HI | — | +89.30 | — |
| SAFETY_VALVE (lifts; cycles in two_state) | +98.15 | +99.10 | believable (D16) |
| DRUM_LVL_HIHI → turbine trip | — | +100.55 | — |
| FREQ_HI | — | +102.60 | — |
| DRUM_LVL_LO | +112.70 | +202.90 | — |
| **DRUM_LVL_LOLO → MFT → plant dead** | **+127.50** | **+223.40** | required ✓ |

- First-out, two_state: CP1_TRIP:overload → FP1_SUCTION → FP1_TRIP:FP1_SUCTION →
  DRUM_LVL_LOLO.
- First-out, AB: the same, with DRUM_LVL_HIHI before LOLO.
- Safety-valve relief: 916.2 kg (two_state), 11 391.0 kg (AB).
- The dead plant's end-of-run energy residual (−28.49 % / +99.97 %) is the known
  transient behaviour of a steady-state diagnostic, not an audit failure.
- Phase-1 analysis, not re-derived for 0.4.0: the DA buffer consumes most (≈85 s at
  0.1.0) of the time to first trip, as the phase-1 plan intended.

`cp1_trip_recovered` (CP-2 started +12 s): zero alarm transitions in both fidelities.
Mass drift 0.0000 %. Energy residual +0.024 % (two_state) / −0.004 % (AB) of firing.

`load_step`: zero alarm transitions in both fidelities. Δf and swell are in T6/T9 above.
The step is **+6.83 MW** (non-vital demand 47.17 → 54 MW; see Known issues).

## Reference design point, achieved values

`scripts/steady_state.py` (60 MW commanded). Unchanged by 0.4.0 to the printed digit:

| Quantity | Plan | Achieved | Note |
|---|---|---|---|
| Electrical output | 60 MW | 60.000 MW | |
| Drum pressure | 8.0 MPa | 8.0000 MPa | Tsat 295.06 °C |
| Turbine steam flow | ≈77 kg/s | 76.923 kg/s | |
| Pegging (aux) steam | — | 10.198 kg/s | D5 |
| Feedwater flow | — | 87.121 kg/s | = steam + pegging |
| Firing heat (effective) | ≈180 MW | **199.593 MW** | plan's formula omits DA heating; D5 |
| Condenser duty | — | 139.593 MW | 7.000 kPa at rated |
| Energy closure | <2 % | 0.0000 % | |
| fw valve / throttle / firing / DA LCV | — | 0.5528 / 0.8500 / 0.8009 / 0.5999 | |
| NPSH margin FP1 / CP1 | — | 2.70 m / 1.00 m | CP trip at 0.25 m (M5b) |
| Total water inventory | — | 27.81 t | two_state; AB 51.5 t |

| Turbine (M2) | Value |
|---|---|
| eta_t (derived) | 0.799126 |
| w at design (8.0000 MPa → 7.0000 kPa) | 780.000 kJ/kg |
| ∂w/∂p_cond | −11.026 J/kg/Pa = **−1.414 %/kPa** = −4.787 %/inHg |
| ∂w/∂p_drum | +4918.579 J/kg/MPa = +0.631 %/MPa |

Sizing-rule compliance (phase 1, unchanged): DA working inventory ≈6.9 t ≈ 79 s of
rated feed (rule ≥60 s). Hotwell ±0.5 m band ≈4.0 t ≈ 52 s of condensate (rule
≥45 s). Drum NWL to LOLO ≈3.47 t ≈ 45 s of steam with feed lost (rule 25–60 s).

## Parameter / tuning decisions and rationale

All values are in `src/hotwell/data/baseline.yaml` unless noted.

- **Drum level PI** kp 3.0, ki 0.05 (Ti 60 s): the valve-to-level plant is an
  integrator; ~20 s closed loop.
- **Three-element trim (AB default)** kp 30 kg/s/m, ki 0.075 (Ti 400 s), ±25 kg/s.
  Retuned in M4b from kp 15 / ki 0.15. Stability criterion: Ti > κ·ρA ≈ 116 s
  (D25).
- **Drum pressure PI** kp 1.8e-7 1/Pa, ki 3e-9 (~12 s): tight enough that losing the
  10.2 kg/s pegging draw on a CP trip peaks at DRUM_P_HI, not the safety valve.
- **DA level PI** kp 1.5, ki 0.025.
- **Hotwell level PI (M5b)** setpoint −0.15 m, kp 13, ki 0.044,
  `anti_windup: conditional`, I = 0 at init (D26). It sits exactly closed in normal
  operation.
- **Governor** pure droop R = 0.05, x_cmd scaled by x_rated = 0.85 (D6).
- **Turbine** `w_design` 780 kJ/kg; eta_t derived so w equals it at the design state
  (D22). k_t = P_rated/(x_rated·w_design·p_drum) keeps droop, rated flow and rated
  power consistent.
- **Firing ceiling** q_fuel_max 280 MW, eta_comb 0.89.
- **FP NPSH_req deliberately flat** (a 9.8 m, b 59.6), so DA drain-down crosses the
  0.5 m trip ≈95 s after condensate loss.
- **Pump curves** shutoff = 1.25 × own rated head. The FP has a 20 % flow margin over
  service; that margin is load-bearing for the load step.
- **Valves** FRV Cv 0.1495 (x ≈ 0.55 at rated); LCV Cv 0.38295 (x ≈ 0.60). Makeup
  valve Cv is derived so wide open passes `makeup.capacity_design` 10 kg/s at design
  vacuum.
- **Makeup source (M5b)** CST at atmospheric, 30 °C, z 5.0 m, unlimited. Vacuum
  drag-in Δp = p_atm + ρgz − p_cond.
- **Protection additions** COND_P_HIHI 18 kPa / 5 s, latching → turbine trip (Q2).
  CP1/CP2_SUCTION NPSH margin < 0.25 m / 5 s, latching → trip that pump.
- **Procedure thresholds (M6)**:
  - NOP-03 trim gain 20 MW/Hz (plant 21.5: monotone convergence), max step 2 MW,
    settle 30 s, deadband 0.02 Hz.
  - NOP-01 parallel-run floor condensate_flow > 20 kg/s, CP NPSH > 0.5 m (D32).

## Decisions taken under ask-vs-decide

D1–D19 are phase 1 (0.1.0); D20 onward are 0.4.0.

- **D1 — property source**: typed-in standard steam-table points (Moran/Shapiro,
  Cengel/Boles tabulations of IAPWS) rather than ad-hoc CoolProp; internal energies
  derived as u = h − p·v. 0.4.0 adds an optional IAPWS-97 audit
  (`scripts/audit_steam_props.py`; M2 result: worst 0.074 %, the 0.3.0 psat table;
  new M2 entries ≤ 0.025 %. Not re-run for the release: `iapws` is not installed in
  this venv).
- **D2 — extra low-range fits** `hf_t(T)`, `rho_f_t(T)`, inverse `tsat_lowp(p)`. M2
  adds `s_f(p)`, `s_g(p)` (derived as s_f + h_fg/T, not typed), `sf_t(T)`, `hg_t(T)`.
- **D3 — temperatures in kelvin** throughout the API.
- **D4 — analytic property derivatives** emitted alongside the fits, FD-verified.
- **D5 — DA pegging steam** closes the energy audit. Firing at rated is 199.6 MW, not
  the reference table's ≈180 MW. Alternative rejected: an unmodelled audit input.
- **D6 — droop law scaled by x_rated** so rated load at f0 sits at exactly 60 Hz.
- **D7 — steady-state root formulation**: loop-equilibrium conditions replace the
  degenerate actuator rows and the dependent hotwell row.
- **D8 — hotwell/DA are fixed-temperature saturated reservoirs** (mass-only).
- **D9 — chest holdup counted in the mass audit.**
- **D10 — turbine trip = breaker opens = bus dead**: pumps trip on bus_dead.
- **D11 — sensing runs right after RK4**, before the event layer, so protection consumes
  sensed values.
- **D12 — trip slams are instantaneous position jumps** (separate trip valves).
- **D13 — `set_load` scenario event** (M4 adds `ramp_s`).
- **D14 — `trips.reset` semantics**: clears latches whose condition cleared;
  scenario-injected pump trips have no latch.
- **D15 — T6 evaluated against measured ΔP_e**, not the commanded step.
- **D16 — post-feed-loss safety-valve lift accepted as believable.** Alternative
  rejected: a loss-of-feed MFT.
- **D17 — AstromBellDrum parameter provenance**: Astrom & Bell (2000) eq. set and
  P16-G16 parameters scaled by 0.968; implicit values documented in code and locked by
  a design-point test.
- **D18 — single-element level control is unstable with the AB drum + our cold feed**
  (−0.166 m³ of sub-surface steam per sustained kg/s of feed; the level rises when
  feed is cut). *0.4.0 correction:* the AB + three-element pairing chosen here was
  itself unstable, ζ ≈ −0.02 at a ~1890 s period, which the 1800 s window could not
  show. The "aggressive trim" failure (kp 60, ki 1.5) was Ti = 40 s < κρA, an
  integral-time problem, not too much gain. Fixed by D25.
- **D19 — the path-flow solver converges on step size** (|Δq| < 1e-13·q_hi), so outer
  finite differences see a smooth plant function.
- **D20 — two hashes (M0).**
  - The state hash answers "is the physics unchanged".
  - The observation hash answers "is the exported data unchanged". It covers sensed
    values, indications and alarm states including ack (Alan's amendment).
  - Quantization absorbs sub-LSB truth differences: a 1e-7 relative kp change moves
    the state hash but not the observation hash.
- **D21 — numpy is part of the determinism contract (M1).**
  `test_pinned_raw_draws_numpy_version_gate` pins raw PCG64 and `normal()` draws under
  numpy 2.5.1. Determinism scope: seed + scenario + platform + numpy version.
- **D22 — turbine work (M2, Q1).**
  - Definition: w = eta_t·Δh_s(p_drum → p_cond), saturated drum vapour into the wet
    region. eta_t is derived, not typed.
  - Size: −1.414 %/kPa at 7 kPa is the ideal isentropic slope (∂h/∂p|_s = v),
    checked against Clapeyron.
  - It is steeper than large-unit rules of thumb because exhaust and leaving losses
    are not modelled.
  - The plan's −1.1 %/kPa was a 7→12.35 kPa chord.
  - Config key `turbine.w_spec` → `w_design`, because it is no longer the work at
    every state.
- **D23 — fixed draws per step (I2, M3).** Every instrument draws one standard normal
  from its stream every step, whatever its sigma, fault or plant state, so faulted and
  fault-free twins share noise. Cost: +2 % wall with noise off.
- **D24 — config path `loads.noise.<block>`** (plan said `loads.<block>.noise`) because
  `loads:` is flat. OU deviation starts at 0, since a stationary start would be a
  load step at t = 0⁺.
- **D25 — AB + 3E trim retune (M4b).** Reduced model:
  - L = M/ρA − κF, F = PI(−L), κ ≈ 8.6 mm per kg/s, ρA ≈ 13.5 t/m.
  - Unstable iff Ti = kp/ki < κ·ρA ≈ 116 s; the old tuning had Ti 100 s.
  - Predictions vs measurement (M4b runs of `scripts/level_mode_ringdown.py`, not
    re-run for the release; the slow-set ring-down gates are): predicted ζ −0.028 at
    a 1760 s period, measured
    −0.022 … −0.028 at 1890 s. The predicted threshold at ki 0.15 was kp ≈ 17.3, and
    the ring-down brackets it: kp 16.5 → ζ −0.010, kp 18.5 → +0.011.
  - **Pegging-steam feedforward (approved first) was rejected on evidence**: feeding
    the true pegging flow forward stayed unstable (ζ −0.023 … −0.031). A constant
    offset cannot change a linear mode's stability.
- **D26 — conditional anti-windup on the hotwell loop only (M5b, found by gate G1).**
  Back-calculation absorbed −kp·e while the makeup valve sat closed during a CP
  outage (I ≈ +8) and kicked the valve open with the level above setpoint. The default
  stays `backcalc` for every other loop.
- **D27 — M5b G2 gated on time means over 6000–11000 s** (spec deviation, recorded):
  the loop hunts on the 1 mm level resolution (makeup 0.84–1.18 kg/s around 1.00), a
  quantization limit cycle.
- **D28 — procedure design (M6).**
  - Step kinds do / hold / trim / ack_active; contingencies via goto.
  - Fixed 5 s reaction by default, lognormal from the `operator` stream when
    `reaction_sigma > 0`.
  - `alarm.ack` one per tick, because there is one key per action dict.
  - No casualty response.
- **D29 — manual provenance cites `path::Symbol`, not `file:line` (M7).** Lines rot on
  every edit; symbols are checked mechanically by the sync test.
- **D30 — manual tables name protection actions in operator words** ("trip CP-1"),
  because `trip_pump` is also a fault-event name, which the answer-key hygiene check
  forbids.
- **D31 — `hotwell.units` keeps pump currents in amperes** (the panel shows % rated).
  The constants are otherwise copied from the panel's `displayunits.py`. There are two
  copies until the panel migrates.
- **D32 — absolute flow thresholds in procedures must hold at minimum load (M6).**
  NOP-01's `condensate_flow > 50 kg/s` aborted a correct swap at the 36 MW trough
  (47.2 kg/s). It is now a 20 kg/s floor; the DA level and CP NPSH margins carry the
  real check.

## Known issues / rough edges

- **`load_step` has been a +6.83 MW step since 0.3.0, not the original +6 MW.**
  Kept as is and re-documented (Alan, 2026-11-07), so no golden hash moves.
  - Mechanism: init gives the blocks `load_mw − station_service` (non-vital 47.17 MW,
    vital 11.79 MW), and the scenario sets an absolute non-vital `p0` of 54 MW.
  - Measured ΔP_e is 6.362 MW. T6 compares against measured ΔP_e (D15).
  - The scenario comment, test docstrings and script descriptions were corrected
    after the 0.4.0 tag. The other absolute 54 MW events from a 60 MW init
    (`level_mode_ringdown.py`, `test_m5_faults.py`) are the same +6.83 MW step.
  - T9 is a different mechanism (governor load reference 54 → 60 MW) and is a true
    +6 MW step.
- **AB quiet day: hotwell peaks near +0.24 m after the ramp down to 36 MW** (≈1.9 t of
  inventory leaves the drum). It is inside the ±0.5 m alarm band. Observed in M4b, not
  investigated.
- **Any PI that sits at a limit for long periods has the D26 exposure** under the
  default back-calculation anti-windup.
- **Governor and hotwell loops dither on sensor resolution**: ±0.05 MW from the 0.01 Hz
  frequency LSB, and makeup 0.84–1.18 kg/s from the 1 mm level LSB. This is an honest
  quantization limit cycle.
- **Steady-state init station-service fixed point stops within 1 kW**, so the solved
  state sits +1.0e-4 kg/s / +80 W off the exact design flow (0.3.0 as well).
- **Not modelled** (also manual chapter 08):
  - throttling loss across the governor valve;
  - exhaust and leaving losses;
  - blowdown;
  - carryover;
  - DA pressure dynamics;
  - post-trip heat loss: the dead plant's drum sits near 8.3–8.4 MPa;
  - cold startup.
- **The `v0.3.0` tag's tree has no LICENSE file** (the MIT license commit came after
  it). `v0.4.0` does.

## For future investigation

Recorded on Alan's direction (2026-11-07); deliberately not pursued in 0.4.0.

- **T2 steady-state drift since 0.3.0.**
  - Worst 600 s drift by version: 0.0000 % at 0.2.0 (`c88af5d`), 0.0266 % at 0.3.0,
    0.0283 % at 0.4.0, against a 1 % gate. In all three the init residual is
    2.910e-16 1/s.
  - Ruled out: the 1 kW station-service fixed-point stop. Its +1.0e-4 kg/s flow
    offset gives ≈0.06 kg over 600 s against the observed −1.0 kg of `drum.M`.
  - The mechanism is unknown. The 0.4.0 plan §0 still quotes the stale
    "< 0.001 % of span".
  - Suggested first step: the drift appears in a single commit, `9464eb2` (0.3.0,
    station-service pump motor loads; its parent `c88af5d` shows 0.0000 %). Compare
    `tests/test_steady_state.py -s` per-state drift across it and trace which
    station-service term differs between the init solve and the stepped plant.

## Questions for Alan

None open for the core. The bench plan's questions were answered on 2026-11-07
(`../hotwell-bench/PLAN-bench-0.1.md`).

## Notes for the panel phase

The panel runs 0.3.0. Migrating to 0.4.0 is a separate panel task:

- **Replays:** 0.3.0 session logs will not replay (M2 physics; M4b for AB). Re-measure
  the casualty pins from the table above; the AB column is the panel default.
- **Annunciator:** 22 windows (was 19): `COND_P_HIHI` (legend `COND PRESS / HIGH
  HIGH`), `CP1_SUCTION`, `CP2_SUCTION`.
- **Gauges:** +4 (`makeup_flow`, `makeup_valve_pos`, `cp1_npsh_margin`,
  `cp2_npsh_margin`); `OBSERVATION_SPEC` is 26 instruments, appended.
- **Mimic:** a makeup valve with a CST terminal.
- **Controller stations:** a hotwell-level loop station (`loop.hotwell_level.mode`,
  `makeup_valve.manual_cmd`).
- **Adopt** `hotwell.units` (one conversion table) and `hotwell.recorder` (replaces
  `sessionlog.py`).
- **Pin:** bump the dependency pin to `@v0.4.0`. The README no longer suggests
  `-e ../hotwell`.

Standing contract notes from phase 1, all still true:
- Alarm transitions are not in the fired-action list. Diff `Observation.alarms` step
  over step, as `run_scenario.py` does.
- First-out entries include free-form labels (`CP1_TRIP:overload`) that are not table
  ids.
- `step()` applies scenario events before submitted actions. `hotwell.recorder`
  encodes that order.
- Frequency range is 50–70 Hz so the 66 Hz overspeed is observable.
- Historian `query()` is strip-chart-shaped (20 Hz trailing 10 min, 1 Hz beyond).
- `drum.model` and `control.drum_level.three_element` are fidelity switches. AB +
  single-element is a casualty-inducing configuration (D18).

## Notes for the bench phase

**Repo and pinning.**
- hotwell-bench consumes `hotwell @ …@v0.4.0` plus an exact numpy pin (D21).
- Released item sets record the hotwell commit, the numpy version and per-item state
  and observation hashes.
- hotwell is public; the bench's secrecy rests on held-out seeds and the answer key.

**Stream IDs** (`hotwell.rng.STREAM_IDS`, append-only, pinned in `tests/test_rng.py`;
`SeedSequence([seed, id])`):

| Stream | ID |
|---|---|
| `sensor.<instrument>`, in `OBSERVATION_SPEC` order (drum_pressure … fp2_npsh_margin) | 1000–1021 |
| `sensor.makeup_flow`, `sensor.makeup_valve_pos`, `sensor.cp1_npsh_margin`, `sensor.cp2_npsh_margin` | 1022–1025 |
| `load.vital`, `load.nonvital` | 2000, 2001 |
| `operator` (ProcedureRunner reaction delays) | 3000 |

The bench should draw its own item parameters from its own seed tree, never from
these.

**What a dump may contain** (I5):
- `Observation` values (26 instruments), indications, and alarms;
- or historian signals minus `hotwell.historian.TRUTH_SIGNALS` = {`m_leak`, `m_peg`,
  `m_relief`, `p_mech`, `q_fire`}.

`INDICATION_SIGNALS` = {`alarm_count`, `breaker_closed`, `cp1_mode`, `cp2_mode`,
`fp1_mode`, `fp2_mode`, `mft`, `nonvital_connected`, `plant_dead`, `safety_open`,
`turbine_trip`}. Two quirks:
- `safety_open` ≡ indication `safety_valve_open`;
- `<pump>_mode` separates *starting* from *stopped*, which the lamps don't.

Noise is a config (plant) property: set it through the config dict, not the scenario.

**Fault catalog** (`hotwell.faults`, scenario events; factors exactly 1.0 = healthy):

| Event | Targets | Parameter |
|---|---|---|
| `pump_degrade` | cp1 cp2 fp1 fp2 | head_factor |
| `valve_degrade` | frv lcv makeup_valve | cv_factor |
| `actuator_stuck` | fw_valve throttle firing da_lcv makeup_valve | optional t_end |
| `actuator_slow` | fw_valve throttle firing | rate_factor |
| `firing_degrade` | — | eta_factor |
| `condenser_fouling` | — | slope_factor |
| `tube_leak` | — | m_dot_design [kg/s] |

All of these take an optional `ramp_s`. Sensor faults (`sensor_fault`) come in five
kinds: `stuck`, `bias`, `drift` (`rate`, `max_bias`), `lag` (`tau_s`) and
`noise_increase` (`factor`).

**Detectability sweep** (`scripts/fault_detectability.py`, re-run for this release;
every row reproduced the M5/M5b values):
- Setup: constant 60 MW, the quiet-day noise preset, seed 42, step onset at 300 s,
  1 h window.
- Detected = the faulted − fault-free twin difference exceeds max(3σ, 2 LSB) for
  10 consecutive 1 Hz samples.
- It is an **optimistic oracle bound** (no model sees the twin) and covers steps only.
  Ramped onsets are unswept.
- Delay after onset, two_state + 1E | AB + 3E:

```
fault                       mag     2S+1E delay  first instr.     | AB+3E delay  first instr.
pump_degrade fp1          0.995       6 s  fp1_current             |     2 s  fw_valve_pos
pump_degrade fp1           0.99       1 s  feed_flow               |     2 s  fw_valve_pos
pump_degrade fp1     0.98, 0.97       1 s  feed_flow               |     1 s  fp1_current
pump_degrade cp1           0.99      27 s  da_lcv_pos              |    23 s  da_lcv_pos
pump_degrade cp1     ≤ 0.98           1 s  condensate_flow         |     1 s  condensate_flow
valve_degrade frv          0.99       n/d                          |     n/d
valve_degrade frv          0.98      34 s  da_lcv_pos              |     2 s  fw_valve_pos
valve_degrade frv          0.95       1 s  feed_flow               |     2 s  fw_valve_pos
valve_degrade frv           0.9       1 s  feed_flow               |     1 s  fw_valve_pos
valve_degrade lcv          0.99       n/d                          |     n/d
valve_degrade lcv          0.98      27 s  da_lcv_pos              |    28 s  da_lcv_pos
valve_degrade lcv    ≤ 0.95           1 s  condensate_flow         |     1 s  condensate_flow
firing_degrade     0.998, 0.995       n/d                          |     n/d
firing_degrade             0.99      15 s  drum_pressure           |    99 s  firing_rate
firing_degrade             0.98       7 s  drum_pressure           |    21 s  fw_valve_pos
condenser_fouling   1.05, 1.1         n/d                          |     n/d
condenser_fouling  1.25, 1.5          1 s  cond_pressure           |     1 s  cond_pressure
actuator_slow (fw_valve, throttle, firing; 0.5, 0.2, 0.05)  n/d    |     n/d
actuator_stuck fw_valve             456 s  da_lcv_pos              |     4 s  fw_valve_pos
actuator_stuck throttle               6 s  frequency               |     6 s  frequency
actuator_stuck firing                26 s  drum_pressure           |   115 s  fw_valve_pos
actuator_stuck da_lcv                32 s  da_lcv_pos              |    36 s  da_lcv_pos
tube_leak                   0.1     524 s  hotwell_level           |   689 s  hotwell_level
tube_leak                   0.3     192 s  hotwell_level           |   388 s  hotwell_level
tube_leak                   1.0      40 s  fw_valve_pos            |   123 s  drum_level
tube_leak                   3.0      13 s  fw_valve_pos            |    44 s  drum_level
```

(Rows with identical results are merged; the script prints one row per magnitude.)

Readings for item design:
1. **actuator_slow is undetectable at constant load** at every factor. It needs a
   transient: a ramp or a background operation.
2. **A stuck FRV takes 456 s under 1E but 4 s under 3E.** The 3E loop dithers the
   valve on feed-flow noise, so a stuck valve shows as the dither stopping.
3. A degraded pump is visible only while it runs: swapping off a degraded FP-1
   restores the FRV position (0.5528 → 0.6519 → 0.5534; M5 test). Background swaps
   are diagnostic.
4. FP-1 head loss and FRV Cv loss both open the FRV. FP-1 current and a later swap
   separate them, and only sometimes: a confusion pair.
5. Many 1 s detections are the step transient itself.
6. A small leak shows first as the hotwell trend; larger ones through the feed side.

**Control instability as a fault class.** Ti = κ·ρA ≈ 116 s (D25) is a designable
stability boundary for the AB + 3E trim. An injected mis-tune, or phase lag in the loop
(a sensor `lag` on drum_level or feed_flow), should produce a growing ~30 min
oscillation at a predictable rate against a stable baseline. Not built or swept.

**Quiet-day statistics** (`scripts/quiet_day.py`, closed-loop operator, seed 42, release
run):

| | two_state + 1E | AB + 3E |
|---|---|---|
| result | PASS | PASS |
| wall for 24 h | 393.0 s (220×) | 440.2 s (196×) |
| trips / rejected actions | none / 0 | none / 0 |
| mass audit drift | +0.00000 % | −0.00000 % |
| alarm transitions | 0 | 0 |
| makeup valve max command | 0.0 | 0.0 |
| NOP-01 (CP swap) / NOP-02 (FP swap) | completed 06:00:05–06:03:36 / 18:00:35–18:04:07 | same |
| sensed frequency [Hz] | 59.80 @ 18.02 h … 60.16 @ 3.50 h | 59.85 @ 10.82 h … 60.16 @ 3.50 h |
| sensed drum level [mm] | −38 @ 18.05 h … +55 @ 18.02 h | −36 @ 10.39 h … +37 @ 3.25 h |
| sensed drum pressure [MPa] | 7.56 @ 18.02 h … **8.38 @ 18.04 h** | 7.90 @ 10.32 h … 8.10 @ 3.14 h |
| sensed DA level [m] | −0.128 … +0.126 (both at the FP swap) | −0.016 … +0.014 |
| sensed hotwell level [m] | −0.048 … +0.038 | −0.020 … **+0.244 @ 4.24 h** |
| sensed condenser pressure [kPa] | 6.10 @ 8.08 h … 7.25 @ 0.77 h | same |
| sensed FP-1 NPSH margin min [m] | 2.55 | 2.55 |
| sensed MW out | 34.6 … 61.1 | 34.6 … 61.1 |
| state hash | `90b95ce5…` | `e05dc79d…` |

What these extrema show (not captured in M6; first seen in this release run):
- **In two_state + 1E the 18:00 feed-pump swap is the day's largest transient**:
  drum pressure 7.56 → 8.38 MPa within ~1 min, against DRUM_P_HI at 8.40 MPa / 2 s.
  That is a 2-LSB margin, so another seed may alarm during a routine swap. Under
  AB + 3E the swap does not reach the day's extrema. Not investigated. The bench
  plan proposes AB + 3E items.
- **Clamped instruments read biased near their floor.** `makeup_flow` has σ 0.05 kg/s,
  is clamped at 0 and has 0.1 kg/s resolution, so a true zero reads up to 0.2 kg/s. A
  model may read that as makeup in use; it is noise.
- NOP-03 completed 287/287 in both. Trims that needed moves: 116 (two_state) and 112
  (AB) in the M6 run; this run's printout lists each trim but not the count.

The noise preset (`QUIET_DAY_SENSOR_NOISE`, `QUIET_DAY_LOAD_NOISE`) is **provisional**:
plausible orders of magnitude, not calibrated instrument data. The bench owns item
noise levels.

**The manual is an ablation knob** (with / without). Its abnormal procedures are
symptom-based, and `test_manual_sync.py` forbids fault-event names in it.

## Release history (summary; full detail in CHANGELOG)

- **0.4.0 (2026-11-07)** — this document.
- **0.3.0 (2026-08-29)** — station-service pump motor loads on the islanded bus.
  Scenario `load_mw` stays the commanded gross output. Station service at 60 MW is
  1040.7 kW. FP-2 start +0.33 MW on the meter; CP-2 start +23 kW, below the meter's
  0.1 MW resolution.
- **0.2.0 (2026-07-26)** — panel precursor, no physics change:
  - manual trip actions `trips.manual_mft` / `trips.manual_turbine` (same code path
    as protection);
  - annunciator `label:` legends;
  - package-data migration to `src/hotwell/data/`.

  Testing note worth keeping: under an editable install a chdir test proves nothing,
  so `tests/test_packaging.py` asserts that resources resolve inside the installed
  package.
- **0.1.0 (2026-07-26)** — phase 1:
  - core simulator;
  - AB drum and three-element control;
  - T1–T12.
