# HANDOFF — hotwell phase 1

## 0.4.0 — in progress (branch `release-0.4`, 2026-11-07)

Benchmark-readiness release per `PLAN-0.4-benchmark-core.md` (approved, Q1–Q5
answered there). Milestone status is in `.plan-checkpoint.md`.

- **M0 complete — golden hashes.** Six canonical runs (3 scenarios × 2
  fidelities) pinned from pristine 0.3.0 in `tests/test_golden_hashes.py`;
  regenerate with `scripts/golden_hashes.py [SRC]`. Run lengths: two_state
  `cp1_trip_unrecovered` dies at t = 427.30 s (MFT +127.3 s after the trip),
  AB+3E at 522.90 s (+222.9 s); the other four run to max_t = 900 s.
  New `Simulator.observation_hash` covers what a consumer saw.
  **The two hashes differ in sensitivity:** a 1e-7 relative kp change moves the
  state hash but not the observation hash (quantization absorbs sub-LSB
  differences in truth). Use the state hash for "physics unchanged" and the
  observation hash for "the exported data is unchanged".
- **M1 complete — rng streams.** `hotwell.rng.StreamBank` / `STREAM_IDS`
  (append-only, pinned in `tests/test_rng.py`; a coverage test fails when a new
  instrument has no `sensor.*` stream, which M5b's `makeup_flow` will hit by
  design). Golden hashes unchanged. **Numpy is now part of the determinism
  contract** once noise lands (M3): `test_pinned_raw_draws_numpy_version_gate`
  fails on a numpy that changes PCG64/SeedSequence or the `normal()`
  algorithm. The bench repo should pin numpy for released item sets.

## 0.3.0 — station-service pump loads (2026-08-29)

Requested from panel play: starting a pump did not move the MW meter. Running
pump motors now load the islanded bus (`CHANGELOG.md` has the mechanism and
config keys). Key semantics: **scenario `load_mw` remains the commanded gross
output** — the abstract blocks absorb `load_mw − station_service` at init, so
the 60 Hz droop equilibrium and the §5.1 display anchors are unchanged
(sensed at t = 0: mw_out 60.000 MW, 60.0000 Hz, steam 76.900, feed 87.100
kg/s). Suite: `61 passed` (55 from 0.2.0 + 6 new), ruff clean.

Magnitudes at 60 MW: station service 1040.7 kW (CP-1 + FP-1). FP-2 start
moves the meter (+0.33 MW settled); CP-2 start is +23 kW — real, but below
the 0.1 MW meter resolution (honest for a 40 m-head condensate system; the
ammeter is the visible cue). Trip effects now include losing ~1 MW of motor
load when a feed pump trips mid-cascade.

The canonical timings below were re-measured under 0.3.0
(`scripts/run_scenario.py <scenario> --events`); every shift is ≤ 0.2 s and
the first-out chains are unchanged. 0.2.0 session hashes do not reproduce
under 0.3.0 (physics change).

## 0.2.0 — panel precursor (2026-07-26)

Released for the `hotwell-panel` repo per PLAN-panel.md §11. **No physics
changed**; the canonical casualty timings below are unchanged (verified from a
wheel install: FP1_SUCTION still fires at +92.65 s after the CP-1 trip).
Suite: `55 passed` (37 from 0.1.0 unchanged + 18 new), ruff clean.
Full detail in `CHANGELOG.md`.

1. **Manual trip actions** `trips.manual_mft`, `trips.manual_turbine`. Identical
   in effect to the protective actions — `_do_mft` / `_do_turbine_trip` were
   extracted from `_apply_protective_actions` as a behavior-neutral refactor
   (37 tests green before the actions were added), so both paths run the same
   code. First-out records `MANUAL_MFT` / `MANUAL_TURBINE_TRIP`. Re-pressing an
   already-latched trip is rejected-and-recorded. Manual trips hold no engine
   latch, so `trips.reset` clears them — same convention as scenario-injected
   pump trips (D14).
2. **Annunciator legends**: optional `label:` (1–2 lines, ≤ 12 chars) per
   protection-table entry, defaulting to the id via `Condition.legend`. All 19
   shipped conditions carry one; widest line is 12 chars (`SAFETY VALVE`).
   Display-only — the engine never reads it.
3. **Package-data migration**: `configs/baseline.yaml`, `data/protection.yaml`,
   and `scenarios/*.yaml` now live in `src/hotwell/data/`, behind
   `hotwell.data.{baseline_config_path, protection_table_path,
   builtin_scenarios, read_text}`. All loaders default to the packaged copies
   and still accept a path override. `DEFAULT_CONFIG` and `DEFAULT_TABLE` are
   gone (both were repo-root-relative).

**Testing note worth keeping.** A chdir-to-tmpdir test does *not* prove the
migration: under an editable install `Path(__file__).parents[3]` still resolves
into the checkout, so such a test passes against the pre-migration code.
`tests/test_packaging.py` instead asserts each default resource resolves inside
`Path(hotwell.__file__).parent`, which the old paths cannot satisfy, and the
release was additionally validated by installing a built wheel into a throwaway
venv and running a canonical scenario from a bare directory.

## Status summary

**M4 complete** (on Alan's explicit go-ahead, 2026-07-26; D5/D15 ratified). The
AstromBellDrum (Astrom & Bell, Automatica 36 (2000), fourth-order) is selectable via
`drum.model: astrom_bell`; **T9 is un-skipped and passes** (swell +5.9 mm on a +6 MW
steam-demand step; two-state contrast case confirms monotone). Three-element feedwater
(steam-flow feedforward + feed-flow trim) is behind `control.drum_level.three_element`.
Comparison plot: `scripts/compare_drums.py` → `out/drum_comparison_load_step.png`.
The phase-1 canonical scenarios and their acceptance tests still run on the two_state
default and all pass unchanged.

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
| T9 inverse response | **pass** (M4) | AB drum swell +5.9 mm on +6 MW demand step; two-state contrast −0.0 mm (monotone) |
| T11 performance | **pass** | 1 h simulated in 21.4 s wall (169× real time; budget 60 s — see D19 for why this doubled in M4) |

Suite: `37 passed` (no skips; ~52 s); ruff clean. M4 additions: AB steady hold
(residual 7.5e-16, 300 s drift 0.0000%, audits exact on the 51.5 t AB inventory),
design-point consistency, three-element behavior (load-step level peak 16.4 mm
single-element → 6.2 mm three-element on the two-state drum).

Property fit accuracy (max relative error vs source points, limit 0.5%): worst 0.051 %
(v_f(T)); all others ≤ 0.041 %. Full per-function report in the generated module
docstring.

## Achieved casualty timings vs targets

`cp1_trip_unrecovered` (CP-1 overload trip at t = 300 s), full annunciator sequence:

(Re-measured under 0.3.0 station-service loads, 2026-08-29 —
`python scripts/run_scenario.py cp1_trip_unrecovered --events`. Every event
moved ≤ 0.2 s from the 0.2.0 table; the sequence and first-out are identical.)

| t rel. CP-1 trip | Event | Target |
|---|---|---|
| +19.6 s | DRUM_P_HI alarm (pegging-steam demand lost, transient; clears ~+42 s) | — |
| +23.2 s | DA_LO alarm (DA draining) | — |
| +57.3 s | HOTWELL_HI alarm (condensate backing up) | — |
| **+92.8 s** | **FP1_SUCTION trip** (NPSH margin < 0.5 m sustained 5 s) | **45–120 s** ✓ |
| +98.0 s | SAFETY_VALVE lifts (feed lost at full steam draw; cycles ~5×) | believable (see D16) |
| +112.5 s | DRUM_LVL_LO alarm | — |
| **+127.3 s** | **DRUM_LVL_LOLO → MFT + turbine trip → bus dead → plant_dead** | required ✓ |

The DA buffer consumes ≈85 of the 92.8 s to first trip, as the plan intends.
First-out: CP1_TRIP:overload → FP1_SUCTION → FP1_TRIP:FP1_SUCTION → DRUM_LVL_LOLO.

`cp1_trip_recovered` (CP-2 started +12 s): worst FP NPSH margin 2.3 m over the
whole run (trip at 0.5 m — comfortable no-trip margin; min of the
`fp*_npsh_margin` columns in `run_scenario.py cp1_trip_recovered --csv`),
zero alarms, levels at +300 s after the standby start: drum +1.0 mm,
DA +0.002 m, HW −0.003 m (`test_t8_recovered` print; limit ±50/±100 mm).

`load_step` (+6 MW on non-vital at t = 300 s, 0.3.0 figures from
`run_scenario.py load_step --csv` extrema): f settles 60.000 → 59.690 Hz;
minimum transient 59.32 Hz held under FREQ_LO's 2 s delay, so still no
annunciation (`--events` prints zero transitions); drum pressure dips to
7.63 MPa (alarm at 7.2); drum level max excursion −19 mm.

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

- **Control gains** (`src/hotwell/data/baseline.yaml`, `control:` section) — one line each:
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

## Decisions taken under ask-vs-decide (M4: D17–D19 at the end)

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
- **D17 — AstromBellDrum parameter provenance and scaling.** Equation set transcribed
  from the paper directly (eq. 24 with all e-coefficients, eqs. 12/26 void fraction,
  eq. 15 circulation, eqs. 19–20 level, section 4.8 equilibria) — fetched and read, not
  reproduced from memory. Parameters: the paper's section 5.1 P16-G16 table (V_d 40,
  V_r 37, V_dc 11 m³, A_d 20 m², m_t 300 t, m_r 160 t, k 25, β 0.3, T_d 12 s), volumes/
  areas/masses × **scale = 0.968** = our rated drum draw (87.12 kg/s) / the paper
  plant's estimated full-load steam flow (~90 kg/s, from Fig 3's 180 MW heat-flow axis
  at h_s − h_fw ≈ 2.0 MJ/kg with ~200 degC feed). Values the paper leaves implicit:
  metal C_p = 550 J/(kg·K) (validated against Table 2's m_t·C_p·∂t_s/∂p ≈ 1410 J/Pa at
  8.5 MPa, within 3%); drum metal m_d = 100 t (inferred: m_t − m_r = 140 t covers drum +
  downcomers; its e42 term is small); A_dc = 0.2774 m² calibrated with the paper's k=25
  so q_dc ≈ 1300 kg/s at our design point — giving riser-exit quality α_r = 0.108,
  squarely in the paper's high-load range (Fig 7, ~0.1). V_sd0 = 19.14 m³ is *derived*
  at construction from the section-4.8 V_sd equilibrium with V_sd,nom = 4.8 m³ (paper
  Fig 4 shows ~5) — large because our feed is far more subcooled than the paper
  plant's. Level reference = half-drum below-surface volume. A design-point test locks
  these derivations.
- **D18 — single-element level control is unstable with the AB drum + our cold feed.**
  Cutting feed reduces in-drum condensation, so the sub-surface steam volume grows
  (−0.166 m³ per sustained kg/s of feed) and level RISES — a positive feedback through
  the level loop that ran load_step into DRUM_LVL_HIHI/turbine trip. The short-term
  static gain from feed to level is inverted (~120 s break-even), so the M4 pairing is
  AB + three-element feedwater with a deliberately SLOW trim (kp 15 kg/s/m, ki 0.15,
  ±25 kg/s; an aggressive trim of kp 60/ki 1.5 was demonstrated unstable, peak 719 mm).
  Result: load_step peak +65 mm, no alarms, converging (~+13 mm at t=1800). This is the
  simulation reproducing WHY three-element control exists; the panel phase should treat
  single-element + AB as an operator-visible degraded mode, not a default.
- **D19 — path-flow solver must converge on step size, not residual.** The original
  solve exited on a loose pressure-residual with warm-start-dependent iteration count;
  outer finite differences (scipy hybr's Jacobian) then saw iteration noise instead of
  smooth flow derivatives — found as a near-null fw-valve column stalling the AB
  steady-state root at off-design loads. Now converges to |Δq| < 1e-13·q_hi. Cost:
  T11 went from 11.0 → 21.4 s per simulated hour (still 2.8× inside budget); benefit:
  steady-state residuals back to ~3e-16 for both drum models, and any future
  gradient-based consumer (MPC, trim optimization) gets a smooth plant function.
- **D10 — turbine trip = generator breaker opens = bus dead.** Single generator,
  islanded, no station-service alternative is modeled, so a turbine trip deenergizes
  both load blocks AND the pump motors (pumps trip on "bus_dead"). This is what makes
  MFT + turbine trip terminate a casualty in `plant_dead` (M2 wires the pump-trip
  cascade). Alternative rejected: keeping pumps energized after a turbine trip would
  require a station-service/battery model the plan excludes.

## Known issues / rough edges

- ~~Steady-state root residual ~2e-8 after the M3 feed-pump resize~~ — resolved by the
  D19 solver-smoothness fix; back to ~3e-16.
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
- **Alarm transitions are not in the fired-action list.** `ProtectionEngine._fire`
  emits a `FiredAction` only for non-`alarm` actions, so pure-alarm conditions
  (DRUM_P_HI, DA_LO, HOTWELL_HI, DRUM_LVL_LO — most of the casualty cascade above)
  produce nothing there, and `alarm_states()` returns only non-clear entries, so a
  clear shows up as a *disappearance*. A consumer wanting activate/ack/clear edges
  must diff `Observation.alarms` step over step; `scripts/run_scenario.py` has the
  reference implementation (it builds the timeline strip that way).
- **First-out entries are not all protection-table ids.** `record_external_trip`
  appends free-form labels — `CP1_TRIP:overload`, `FP1_TRIP:FP1_SUCTION`,
  `MANUAL_MFT` — and the canonical casualty's *initiator* is one of them. A panel
  that only maps first-out onto annunciator windows will fail to show the initiating
  event; it needs a separate first-out display path.
- **Actions apply before scenario events within a step?** No — `step()` runs
  `_apply_scenario_events()` first, then submitted actions. Anything replaying a
  live session as a scenario must preserve that relative order for ticks that carry
  both, or the replay diverges.
- `src/hotwell/data/protection.yaml` ids are the annunciator window list; the timeline strip in
  `run_scenario.py` is a preview of the annunciator history display.
- Historian `query(signals, t0, t1, max_points)` is strip-chart-shaped; 20 Hz for the
  trailing 10 min, 1 Hz beyond — matches a panel chart recorder well.
- Frequency instrument range is 50–70 Hz so the 110% overspeed setpoint (66 Hz) is
  observable — a 55–65 Hz gauge would have clamped below the trip point (found during
  design; keep in mind when drawing gauge faces).
- M4: `drum.model` and `control.drum_level.three_element` are config switches the
  panel could expose as "plant fidelity" options; with the AB drum, single-element
  level control is a realistic casualty-inducing configuration (D18) — potentially a
  deliberate training scenario later, not a bug.
