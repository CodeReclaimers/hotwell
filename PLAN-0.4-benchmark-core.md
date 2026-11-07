# hotwell 0.4.0 — Benchmark-Readiness Core Release — Implementation Plan

Status: **APPROVED** (2026-11-07; Q1–Q5 answered, see §4). M0–M1 authorised to start.

## 0. Context and objective

The first evaluation target is **Idea 2**: give a model a 24-hour plant data dump with
one injected fault (or none); it must name the fault and its onset time. hotwell 0.3.0
cannot produce a meaningful item yet:

1. **No stochasticity.** `Simulator.rng` is seeded but nothing draws from it
   (`simulator.py:10`). At steady state the quantized outputs are constant (T2 drift
   < 0.001 % of span), so onset reduces to "first sample that changes".
2. **No operating background.** No load profile, no routine operator activity, so
   every transient is the fault.
3. **The hidden-fault repertoire is thin.** Pump trips are always visible (indications
   are truthful); sensors support only `stuck` and `bias`.
4. **Non-textbook physics.** Turbine specific work is the constant `w_spec`
   (`plant.py:273`, `h_exh = h_g − w_spec`), so condenser backpressure does not affect
   output, and there is no low-vacuum trip.

This release adds the mechanisms. The **item generator, twin-run onset labelling, dump
packaging and grader** go in a new `hotwell-bench` repo (separate plan, after 0.4.0),
which consumes `hotwell` as an installed dependency, the same way `hotwell-panel` does.

Deliverables:

- A. Named, independent rng streams; sensor noise; new sensor fault kinds.
- B. Load ramps and load process noise (the daily profile is built from these by the
  bench repo).
- C. Hidden physical faults, each ramp-able, each audit-closed.
- D. Backpressure-dependent turbine work and a low-vacuum turbine trip, **always on**
  (Alan, 2026-11-07). This is the only milestone that changes physics and breaks hashes.
- E. Structured operating procedures (YAML) and a closed-loop procedure runner (a
  scripted background operator), with a shift log and replay-exact action recording.
- F. Plant description and operator manuals (`docs/manual/`) for humans and agents. SI
  units with US customary in parentheses; every table generated from the contracts,
  with a test that fails when the manual drifts from the code.

## 1. Locked decisions (Alan, 2026-11-07)

- **Gap 4 is fixed and always on**: one physics for every consumer. 0.3.0 hashes stop
  reproducing at M2; the canonical cascade tables in both HANDOFFs are re-measured.
- **Background operations use a closed-loop runner**, not open-loop event expansion.
  The procedure YAML is the single source for both the runner and the manual's normal
  operating procedures.
- **Repo split**: mechanisms, procedures and manuals in `hotwell`; benchmark generation
  and grading in `hotwell-bench`.
- **Manual units**: SI primary, customary in parentheses, from the same affine table
  the panel uses (moved into the core as `hotwell.units`).
- All phase-1 locked decisions still hold (PLAN-sim-core.md §1): fixed-step RK4 at
  20 Hz, discrete state frozen during RK4 stages, determinism, SI internally,
  **controllers and protection act on sensed values**, runtime deps numpy/scipy/pyyaml
  only.

### Invariants this release must preserve (each one gets a test)

- **I1 — Zero means off.** Every new feature at its default (σ = 0, no fault events,
  no runner) is bit-identical to having no feature. Checked against golden hashes.
- **I2 — Stream independence.** Each rng consumer has its own stream, keyed by a
  stable ID. Adding a consumer, or a fault that changes the plant's state, never shifts
  the draws of any other stream. Concretely: **each noise stream draws a fixed number of
  values per step, whether or not that instrument is faulted, stuck, clamped, or the
  plant is dead.** This makes the faulted and unfaulted twins (the bench repo's onset
  labelling) share identical noise realizations.
- **I3 — Audits stay closed.** Every fault that moves mass or energy out of the modelled
  cycle has an explicit audit term. T3/T4 stay exact under each fault.
- **I4 — Indications stay truthful.** Pump run/trip lamps and breaker/MFT/SV flags are
  never faulted in 0.4.0 (out of scope, §9).
- **I5 — No truth in observations.** `Observation` carries sensed values plus truthful
  indications only. The historian's truth-side extras (`m_peg`, `m_relief`, `q_fire`,
  `p_mech`) stay, but are listed in a new `historian.TRUTH_SIGNALS` constant so
  exporters can exclude them mechanically.

## 2. Milestones

Each milestone ends with tests green, ruff clean, HANDOFF + CHANGELOG updated, focused
commits, and a progress-log entry. Never start a milestone with the previous one red.
**Every milestone except M2 is hash-neutral and must pass the golden-hash gate
unchanged.**

### M0 — golden hashes (no behaviour change)

- `tests/test_golden_hashes.py`: the state-history SHA-256 for each canonical scenario
  (`cp1_trip_unrecovered`, `cp1_trip_recovered`, `load_step`) under **both** fidelities
  (two_state + single-element; astrom_bell + three-element), recorded from 0.3.0
  (`9464eb2`) before any edit. Six hashes.
- Add a second hash, `Simulator.observation_hash`, over every sensed observation
  (values in `OBSERVATION_SPEC` order as float64, then indications). Once sensor noise
  exists, the dump's content is what matters, and the state hash alone doesn't cover it.
  Record it alongside the state hashes. New API only; the existing hash is unchanged.
  **Amended 2026-11-07 (Alan): the encoding also covers the alarm list**: each non-clear
  `(id, state)` in table order, so acknowledgement state is included. The observation
  goldens are re-pinned from pristine `9464eb2` in a separate commit before M2; the
  state goldens don't change.
- Gate: suite green; the six state hashes equal hashes computed independently from a
  checkout of `9464eb2` (computed in a scratch worktree, not copied from memory).

### M1 — rng stream plumbing (structural, hash-neutral)

- `hotwell.rng.StreamBank(seed)`: `stream(name) -> np.random.Generator`, built as
  `np.random.default_rng(np.random.SeedSequence([seed, STREAM_IDS[name]]))`.
  `STREAM_IDS` is a frozen, append-only `dict[str, int]` (e.g. `sensor.<instrument>`,
  `load.vital`, `load.nonvital`, `operator`). IDs never change once assigned. Lookups of
  unknown names raise.
- `Simulator.rng` stays for backward compatibility, documented as unused.
- Tests: two banks with the same seed give identical draws per stream; consuming stream
  A does not change stream B's sequence; the ID table is append-only (test pins the
  current table).
- Gate: golden hashes unchanged.

### M2 — backpressure-dependent turbine work + low-vacuum trip (PHYSICS, hash-breaking)

Deliberately isolated: the only change in this milestone is the physics, so any change
in behaviour can be attributed to it.

- **Property fits** (`scripts/gen_steam_props.py`, D1 method: typed IAPWS-derived table
  points with provenance in the generated module): add `s_f(p)`, `s_g(p)` over the
  existing high-pressure range, and `s_f`, `s_g`, `h_g` over the low-pressure range
  (30–150 °C). Same 0.5 % accuracy gate, report in the module docstring.
- **Turbine work**: `w(p_drum, p_cond) = η_t · (h_g(p_drum) − h_2s)`, where
  `x_2s = (s_g(p_drum) − s_f(p_cond)) / (s_g(p_cond) − s_f(p_cond))` and
  `h_2s = h_f(p_cond) + x_2s · (h_g(p_cond) − h_f(p_cond))`. `η_t` is *derived* at
  construction so that `w = 780 kJ/kg` exactly at the design point (8 MPa, 7 kPa). That
  keeps `k_t`, the droop calibration, and the 60 MW / 76.923 kg/s anchors exact.
  `h_exh = h_g − w` stays, so condenser duty and the energy audit follow automatically.
- **Hand estimate to check against the implementation** (steam-table values typed by
  hand, *not* computed by code; the implementation must regenerate and replace these):
  s_g(8 MPa) ≈ 5.743, h_g ≈ 2758 kJ/kg; at 7 kPa x_2s ≈ 0.672, h_2s ≈ 1782 → Δh_s ≈
  976 kJ/kg, η_t ≈ 0.799 (consistent with the config comment "eta 0.80"). At 12.35 kPa
  (50 °C), Δh_s ≈ 920 kJ/kg → w ≈ 735 kJ/kg, i.e. about −5.8 % for +5.35 kPa, roughly
  **−1.1 %/kPa (≈ −3.7 %/inHg)**. That is on the high side of rules of thumb for large
  units, plausible for a small saturated-steam turbine without exhaust-loss modelling.
  Record the code-computed value in HANDOFF.
- **Low-vacuum trip**: new protection entry `COND_P_HIHI` → `turbine_trip`, latching
  (setpoint per Q2). Existing `COND_P_HI` alarm at 12 kPa unchanged.
- Re-measure and re-pin: golden hashes (deliberately; the commit says so), the T6–T8
  numbers, both cascade tables (hotwell HANDOFF and the panel HANDOFF's two-column
  table, via `run_scenario.py --events` under each fidelity), and the design-point
  table (`scripts/steady_state.py`).
- New tests: design-point invariance (w = 780 kJ/kg at 8 MPa / 7 kPa to 1e-9
  relative); `∂w/∂p_cond < 0` and matches a central finite difference; an air-ingress
  step of +5 kPa at rated reduces `mw_out` at fixed load reference by the predicted
  amount (droop accounted for), with a diagnostic printf of the expected vs. measured
  ΔMW; an air-ingress ramp to the COND_P_HIHI setpoint trips the turbine with the
  correct first-out.
- **Panel impact**: `hotwell-panel` uses an editable install of `../hotwell`, so it sees
  this change immediately and its casualty pins go red. See Q3.

### M3 — sensor noise and new sensor fault kinds (hash-neutral at defaults)

- **I5 lands here** (Alan, 2026-11-07): `historian.TRUTH_SIGNALS`, the historian's
  truth-side extras, so exporters can exclude them mechanically. A test asserts that
  every historian signal is either an `OBSERVATION_SPEC` instrument, a truthful
  indication-derived signal, or in `TRUTH_SIGNALS`.

- Config `sensors.noise.<instrument>: {sigma, tau}` in instrument units. `sigma = 0` is
  off (I1). `tau = 0` means white noise; `tau > 0` means AR(1) colored noise
  (discretised OU process at dt, exact `exp(−dt/τ)` coefficient). One draw per
  instrument per step from `sensor.<instrument>` **always** (I2).
- New pipeline order (documented in `sensors.py`):
  `truth → lag(fault) → +bias(fault, possibly ramped) → +noise → stuck override →
  clamp → quantize`. Noise before quantization is intentional: it dithers the rounding.
  (Without noise, rounding is a fixed per-instrument bias of up to ±½ LSB, so a 24 h
  drum mass balance from quantized flows can accumulate a systematic error of order
  0.1 kg/s × 86 400 s ≈ 8.6 t ≈ 0.74 m of equivalent drum level at 11.6 t/m.)
- New fault kinds on the `sensor_fault` event:
  - `drift`: `bias(t) = rate · (t − t_start)`, optional `max_bias`.
  - `lag`: a first-order lag with time constant `tau_s` inserted ahead of the bias
    (plugged impulse line, damped transmitter). This gives F01's "sensor delay" too.
  - `noise_increase`: multiplies `sigma` by `factor` (a degrading transmitter).
  - existing `stuck`, `bias` unchanged.
- Tests: I1 golden; I2 twin test (two runs, one with a `bias` fault on drum_level: the
  noise realizations on every *other* instrument's stream are identical draw for draw,
  checked by recording the raw draws, not the closed-loop sensed values, which
  legitimately differ); white-noise sample σ within 3 % of the configured value over
  10⁴ steps; AR(1) lag-1 autocorrelation within 0.01 of `exp(−dt/τ)`; drift slope
  recovered by least squares; lag step response reaches 63.2 % at τ ± one step.

### M4 — load ramps and load process noise (hash-neutral at defaults)

- `set_load` gains an optional `ramp_s`: a linear ramp from the current `p0` to the
  target over `ramp_s`, evaluated at step boundaries (discrete, frozen during RK4).
- Config `loads.<block>.noise: {sigma_w, tau}`: an OU process on `p0` about its
  scheduled mean, stream `load.<block>`, one draw per step always.
- Tests: ramp endpoint exact and monotone; OU stationary σ and correlation time as in
  M3; I1 golden.
- **"Quiet day" acceptance run** (new script `scripts/quiet_day.py`, test marked
  `slow`): 24 h, with a daily profile of 60 → 36 → 60 MW via ramps (≥ 20 min each),
  noise on, both fidelities, operator frequency trims via the M6 runner (so this
  closes after M6; until then, run it with a fixed load-reference schedule). Pass
  criteria: no protective trips; any alarms enumerated and explained in HANDOFF; mass
  audit drift < 0.1 %; wall time recorded (expected ≈ 8.5 min per 24 h at the T11
  rate; noise overhead ≤ 10 %).

### M5 — hidden physical faults (hash-neutral: only active when events fire)

All faults are scenario events, optionally ramped (`ramp_s`), with parameters stored in
`Discrete` (frozen during RK4, interpolated at step boundaries). A fault at zero
magnitude must be hash-identical to no fault (test).

| Event | Effect | Notes |
|---|---|---|
| `pump_degrade {target, head_factor}` | that pump's `H0 ← H0·f` | impeller wear / recirculation. Per-pump, so it is visible only while that pump runs, which makes swaps diagnostic. |
| `valve_degrade {target: frv\|lcv, cv_factor}` | `Cv ← Cv·f` | partial plugging (f < 1) or trim erosion (f > 1) |
| `actuator_stuck {target: fw_valve\|da_lcv\|throttle\|firing}` | position frozen; the command keeps moving | seized stem. The position *instrument* shows the frozen value (truthful); the controller output (`frame.loops`) does not, which is the clue. |
| `actuator_slow {target, rate_factor}` | rate limit × f | sticky positioner |
| `firing_degrade {eta_factor}` | `eta_comb ← eta·f` | fuel quality / burner fouling: firing rate rises at constant load |
| `condenser_fouling {slope_factor}` | `p_load_slope ← slope·f` | separable from `set_air_ingress` (additive) by load dependence, which the daily profile exercises |
| `tube_leak {m_dot_design}` | drum mass sink ∝ √(p/p_design) at h_f | **see Q5: needs a makeup system** |

- Each fault gets a test: signature direction (e.g. `pump_degrade` on FP-1 lowers its
  delivered head, so the FRV opens further to hold the same feed flow), audit closure under
  the fault, and the zero-magnitude hash identity.
- Bench-relevant data per fault in HANDOFF: the minimum magnitude that is detectable
  within 1 h at the default noise (a rough sweep; the bench repo does the rigorous
  labelling).

### M5b — simple hotwell makeup system (PHYSICS for the hotwell boundary; Q5)

Added on Alan's decision (2026-11-07, Q5). Detailed spec is written and reviewed
before M5b starts. Outline: a makeup valve from a fixed-pressure condensate storage
tank into the hotwell, a hotwell-level PI loop on it (auto/manual, joins
`ACTION_SCHEMA`), a `makeup_flow` instrument (joins `OBSERVATION_SPEC`, which needs a
`sensor.makeup_flow` stream ID), a `CP_SUCTION` protection entry (the phase-1 rough
edge), and the mass/energy audit terms for the makeup boundary. The `tube_leak` fault
in M5 depends on this, so either M5b goes before M5's leak test, or the leak lands
with M5b.

### M6 — procedures and the background-operator runner (no physics; hash-neutral)

- `src/hotwell/data/procedures/*.yaml`. Schema (deliberately the same style as
  `protection.yaml`):
  ```yaml
  id: NOP-02
  title: Feed pump swap (running → standby)
  purpose: ...
  applies_when: [{indication: fp1_running, eq: true}, {indication: fp2_running, eq: false}]
  params: {from: fp1, to: fp2}          # templated, so one procedure covers both directions
  steps:
    - id: s1
      text: Start the standby feed pump.
      do: {"{to}.start": true}
      wait_for: [{indication: "{to}_running", eq: true},
                 {signal: "{to}_current", op: gt, value: 200.0}]
      within: 30.0
      on_timeout: {goto: abort_standby_failed}
    - id: s2
      text: Run in parallel; confirm suction margin on both pumps.
      hold: 60.0
      check: [{signal: "{to}_npsh_margin", op: gt, value: 1.0}]
    ...
  contingencies:
    abort_standby_failed:
      text: Standby failed to start. Leave the running pump in service; report.
      do: {}
      outcome: aborted
  ```
  Conditions are data (signal/indication, op, value), never `eval`. Every `do:` key is
  validated with `actions.check_schema` at load time.
- `hotwell.procedures.ProcedureRunner(procedures, streams, reaction=...)`:
  `start(proc_id, params, t)`, `tick(obs, loops, t) -> dict` (actions for this step),
  `log -> list[LogEntry(t, proc_id, step_id, text, outcome)]`. Operator reaction delay
  between steps is fixed by default or drawn from the `operator` stream (I2). The runner
  reads only `Observation` and `frame.loops`-equivalent loop state (`Simulator.control`
  via a read-only accessor). It never reads truth.
- `hotwell.recorder.ActionRecorder`: drives `sim.step(actions)` and emits a scenario
  YAML whose `action` events carry **half-tick-early** stamps (the panel's proven fix
  for accumulated-float drift: −1.089e−9 s at 36 000 ticks; a 24 h run is 1.728 M
  ticks, so this matters more here). A test confirms that replaying the recorded
  scenario reproduces both hashes, including two actions in the same tick.
  (`hotwell-panel/sessionlog.py` has the reference implementation; the core version
  is new code, and the panel adopting it is a separate panel task.)
- Initial procedures: NOP-01 condensate pump swap, NOP-02 feed pump swap, NOP-03 load
  change with frequency trim (adjust `governor.load_ref_mw` until frequency is within
  60.00 ± 0.02 Hz), NOP-04 alarm acknowledgement. The background operator does **not**
  perform casualty response; that is an item-design choice in the bench repo.
- Tests: swap succeeds with zero rejections and no alarms; the swap meets
  `inhibit_start` on the standby pump → runner aborts, the original pump stays running,
  the log records `aborted` with the step id; replay hash identity; templating fills
  both directions.

### M7 — plant description and operator manuals

`docs/manual/` (markdown, readable by humans and as agent context):

| File | Content | Source |
|---|---|---|
| `00-index.md` | scope, version, how to read | prose |
| `01-plant-description.md` | systems, flow path, design point, equipment data, one-line diagram | prose + **generated** design-point/equipment tables |
| `02-instrumentation.md` | every instrument: range, resolution, SI + customary | **generated** from `OBSERVATION_SPEC` |
| `03-controls.md` | loops, setpoints, modes, three-element scheme, droop/governor, operator controls | prose + **generated** action table from `ACTION_SCHEMA` |
| `04-protection.md` | every condition: setpoint, delay, latching, action | **generated** from `protection.yaml` |
| `05-normal-procedures.md` | NOPs | **rendered** from procedure YAML |
| `06-alarm-response.md` | one section per annunciator id: meaning, probable causes, immediate actions | prose keyed by id |
| `07-abnormal-procedures.md` | symptom-based: loss of condensate pump, loss of feed pump, degrading vacuum, drum-level control abnormal (incl. transmitter failure), FRV/LCV malfunction, frequency excursion, safety-valve lift, post-trip | prose |
| `08-model-limitations.md` | documented simplifications: fixed DA pressure, no carryover, no post-trip heat loss, no motor inrush, pump speed independent of bus frequency, no startup from cold, truthful indications | prose, written from the code |

- `hotwell.units`: the affine SI→customary table (moved from
  `hotwell-panel/displayunits.py`, same exact constants). The panel keeps its copy until
  a panel-side follow-up switches to it with a parity test. Until then there are two
  copies; flagged in HANDOFF.
- `scripts/gen_manual.py` regenerates every block between
  `<!-- BEGIN GENERATED: name -->` / `<!-- END GENERATED -->` markers.
  `tests/test_manual_sync.py` regenerates in memory and fails on any diff. Coverage
  tests: every protection id has a `06` section and vice versa; every procedure renders;
  every action key named in prose exists in `ACTION_SCHEMA`; every instrument name in
  prose exists in `OBSERVATION_SPEC` (catches renamed peripheral references).
- **Writing rule**: prose describing behaviour must be written from the code, citing
  `file:line` in an HTML comment beside each claim (invisible when rendered, auditable
  in review). Any number in prose that isn't in a generated block must come from a
  committed script, named in the same comment.
- **Answer-key hygiene**: the abnormal procedures are symptom-based, the way a real
  plant's are. They do not enumerate the simulator's fault-event library or its
  signatures. The bench repo can then evaluate with and without the manual as an
  ablation.

### Release

Bump to 0.4.0, CHANGELOG (physics change flagged prominently), HANDOFF rewritten per
the phase-1 structure plus a "Notes for the bench phase" section: stream IDs, the
truth-signal list, fault magnitudes and detectability sweep, and quiet-day statistics.

## 3. Out of scope (0.4.0)

The bench repo (generator, onset labelling, packaging, grader, item taxonomy). Faults
on indications/lamps. Makeup/blowdown (unless Q5 says otherwise). Carryover, DA
pressure dynamics, post-trip heat loss, cold startup. Any panel change (the panel
consumes 0.4.0 in a separate task). Performance work beyond keeping T11 and the
quiet-day wall time recorded.

## 4. Decisions on the open questions (Alan, 2026-11-07)

- **Q1 — Inlet-pressure dependence: KEEP.** `w(p_drum, p_cond)` as specified in M2.
- **Q2 — Low-vacuum trip: `COND_P_HIHI` at 18 kPa, 5 s delay, latching →
  `turbine_trip`.** The `cond_pressure` range stays 0–20 kPa.
- **Q3 — APPROVED.** Tag `v0.3.0` at `9464eb2` and reinstall the panel venv from that
  tag (non-editable) **before M2 starts**.
- **Q4 — Fault list APPROVED** as in M5.
- **Q5 — ADD a simple makeup system** (milestone M5b above).
