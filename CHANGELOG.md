# Changelog

## 0.4.0 — unreleased (branch `release-0.4`, plan `PLAN-0.4-benchmark-core.md`)

### Added (M0 — no behaviour change)

- `Simulator.observation_hash`: SHA-256 over every observation `step()`
  returns, encoded by the new public `hotwell.sensors.observation_bytes`
  (sensed values as float64 in `OBSERVATION_SPEC` order, then indications in
  sorted-key order as `key=value\0`, then `#`, then each non-clear alarm in
  table order as `id=state\0`, so ack state is covered; `plant_dead`
  excluded). The existing `state_history_hash` is unchanged.
- `tests/test_golden_hashes.py`: state and observation hashes plus step
  counts for the three canonical scenarios × {two_state + single-element,
  astrom_bell + three-element}, pinned from 0.3.0 (`9464eb2`). Every 0.4.0
  milestone except M2 must leave them unchanged.
- `scripts/golden_hashes.py`: regenerates those values independently
  (observation hash computed outside the simulator), optionally against
  another checkout's `src/`.

### Added (M1 — structural, hash-neutral)

- `hotwell.rng`: `StreamBank(seed).stream(name)` returns a cached
  `numpy.random.Generator` seeded by `SeedSequence([seed, STREAM_IDS[name]])`.
  `STREAM_IDS` is a read-only, **append-only** table of 25 literal IDs:
  `sensor.<instrument>` 1000–1021, `load.vital`/`load.nonvital` 2000–2001,
  `operator` 3000. Unknown names raise `KeyError`; negative seeds raise
  `ValueError`.
- `Simulator.streams`: the run's `StreamBank`. Nothing draws from it yet.

### Added (M4 — hash-neutral at defaults)

- **Load ramps:** `set_load` takes optional `ramp_s`, a linear ramp of the
  block's scheduled `p0` over round(ramp_s/dt) steps with an exact endpoint,
  advanced once per step after events/actions and before the controllers
  (frozen during RK4). A new `set_load` on the same block replaces an active
  ramp, starting from the current value. No `ramp_s` keeps the old step
  behaviour.
- **Load process noise:** config `loads.noise.<block>: {sigma_w [W], tau [s] > 0}`,
  an OU deviation `LoadBlock.p_dev` from the schedule, on stream `load.<block>`.
  It starts at zero (not stationary; see `components/loads.py`). Demand is
  (p0 + p_dev) floored at 0. One draw per block per step always (I2). Empty
  by default.
- `hotwell.components.loads.LoadDriver` (`Simulator.load_driver`); `set_load`
  events are validated at scenario load.
- `scripts/quiet_day.py` + `tests/test_quiet_day.py`: the 24-h acceptance run
  (both fidelities), marked `slow` and excluded from the default `pytest`
  (`pytest -m slow -s`). Registered in `pyproject.toml`.
- `scripts/level_mode_ringdown.py`: ring-down / damping estimate of the slow
  drum-level mode under three-element control.

### Known issue (pre-existing, documented in M4, not fixed)

- AB drum + three-element feedwater: ~1890 s drum-level mode with negative
  damping (ζ ≈ −0.02), the same in 0.3.0. Strict-xfail test
  `test_ab_3e_slow_level_mode_is_damped`. Details in HANDOFF.



- **Sensor noise**, config `sensors.noise.<instrument>: {sigma, tau}`
  (instrument units; `tau = 0` white, `tau > 0` exact AR(1)/OU, started
  stationary). Empty by default (baseline adds an empty `sensors.noise: {}`).
- **Sensor fault kinds** `drift` (`rate`, optional `max_bias`), `lag`
  (`tau_s`, starts at the current truth, no jump), `noise_increase`
  (`factor`); `stuck` and `bias` unchanged. Pipeline order: truth → lag →
  bias/drift → noise → stuck → clamp → quantize. At most one fault per
  instrument.
- **Draw contract (I2)**: every instrument draws one standard normal from
  `sensor.<instrument>` on every `step()`, whatever its sigma, fault or the
  plant state; `SensorBank.last_draws` exposes them. The steady-state init
  sample is noise-free and draws nothing.
- `sensor_fault` events are validated at scenario load (target, kind,
  required params, ranges); `SensorFault` validates itself.
- `hotwell.historian.TRUTH_SIGNALS` (`m_peg`, `m_relief`, `q_fire`, `p_mech`)
  and `INDICATION_SIGNALS` (I5); a test fails on any unclassified historian
  signal.
- `SensorBank(noise=None, streams=None, dt=0.05)`; `sample(t, truth, noisy=True)`.

: every trajectory shifts; 0.3.0 hashes and session logs no longer reproduce**)

- **Turbine specific work depends on drum and condenser pressure.**
  `w = eta_t · Δh_s`, the isentropic drop from saturated vapour at `p_drum`
  to the wet region at `p_cond`; `eta_t` (0.799126) is derived so that `w`
  equals `turbine.w_design` (780 kJ/kg) at the design state, which keeps the
  60 MW / 76.923 kg/s / droop anchors exact. Condenser backpressure now
  costs output: −1.414 %/kPa at rated. `h_exh = h_g − w` keeps the energy
  audit exact. The throttling loss across the governor valve is not modelled.
- **Config key renamed** `turbine.w_spec` → `turbine.w_design`.
  `TurbineParams.w_spec` → `w_design`; `Turbine.p_mech(y)` → `p_mech(y, w)`;
  `Turbine.deriv` takes `w`.
- **Protection: `COND_P_HIHI`** (cond_pressure > 18 kPa for 5 s, latching →
  turbine trip; legend `COND PRESS / HIGH HIGH`). The table has 20 conditions.
- Canonical cascade shifts ≤ 0.30 s; ordering and first-out unchanged (tables
  in HANDOFF).

### Added (M2)

- `hotwell.components.turbine.isentropic_drop(p_in, p_cond)`,
  `Turbine.set_design`, `Turbine.specific_work`, `Turbine.eta_t`.
- Steam-property fits `s_f(p)`, `s_g(p)` (derived s_g = s_f + h_fg/T),
  `sf_t(T)`, `hg_t(T)`; the generator gains an oracle-free s_f transcription
  guard. `scripts/audit_steam_props.py` audits all typed tables and fits
  against IAPWS-97 (optional `iapws`, not a dependency).
- `scripts/run_scenario.py --fidelity two_state_1e|astrom_bell_3e`;
  `scripts/steady_state.py` prints the turbine sensitivities.

### Changed

- `Simulator.rng` is now documented as unused (kept for 0.3.0 compatibility).
  The phase-1 rule "all randomness from one Generator owned by the simulator"
  becomes "all randomness from the simulator's StreamBank".
- Determinism scope stated explicitly: same seed + scenario + platform +
  **numpy version** (NumPy does not promise stable `Generator` distribution
  algorithms across releases; `tests/test_rng.py` pins raw and normal draws
  under numpy 2.5.1 as a loud gate).

## 0.3.0 — 2026-08-29

Station-service pump motor loads on the islanded bus. **Physics change**:
every scenario trajectory shifts (measured shifts in the canonical cascade are
≤ 0.2 s — see HANDOFF); state-history hashes from 0.2.0 sessions do not
reproduce under 0.3.0.

### Added

- **Pump motors load the generator.** Each running or starting pump draws
  `p_motor_rated · (0.25 + 0.75 · p_hyd/p_hyd_rated)` from the bus — the same
  no-load-floor-plus-hydraulic-power shape as the ammeter proxy, so wattage
  and current agree by construction. A stopped or tripped pump draws nothing,
  even while coasting (contactor open); motor inrush is not modeled. The draw
  is frequency-independent, consistent with the pump model whose shaft speed
  does not track bus frequency. New config keys
  `pumps.<class>.p_motor_rated` [W] (condensate 40 kW, feed 1.0 MW in the
  baseline; **0 disables the feature** and restores 0.2.0 behavior).
- `Aux.p_station_service` [W] — the summed draw, part of `Aux.p_elec`.
- `scripts/run_scenario.py --events` prints every alarm transition, so the
  HANDOFF cascade tables regenerate from committed code.

### Changed

- **`load_mw` is the commanded GROSS output, station service included.**
  `initialize_steady_state` sets the abstract blocks to
  `load_mw − p_station_service` by a fixed-point iteration around the root
  solve (contracts ~1/80 per pass; 1 kW tolerance), so the droop equilibrium
  stays exactly at f0 and `mw_out` reads `load_mw` at t = 0. The §5.1 panel
  anchors (76.9 kg/s steam, 87.1 kg/s feed, 60.0 MW at 60.00 Hz) are
  preserved to the displayed digit. The alternative — blocks at full
  `load_mw`, gross 61 MW — was rejected: it invalidates the plan-locked
  anchors.
- `Loads.p_elec` takes a `station_service` term (default 0.0).
- Steady-state init is now gated by the T2-grade equilibrium measure
  (scaled |ydot|max < 1e-7 raises) instead of relying on hybr's
  progress flag, which proved warm-start-history-dependent near convergence.

### Measured (regenerate with the quoted commands)

- 60 MW design point: station service 1040.7 kW (CP-1 + FP-1), blocks
  58.96 MW, `p_elec` 60.000 MW at 60.0000 Hz
  (`pytest tests/test_station_service.py -s`).
- FP-2 start: `p_elec` 60.000 → 60.33 MW (settled; +253 kW station service —
  three-element control pulls the FRV back as the pumps share flow). CP-2
  start: +23 kW — real but below the 0.1 MW meter resolution; the ammeter is
  the visible cue.
- Canonical cascade (`run_scenario.py cp1_trip_unrecovered --events`): every
  event within 0.2 s of the 0.2.0 table; FP1_SUCTION +92.65 → +92.80 s,
  DRUM_LVL_LOLO +127.35 → +127.30 s; first-out chain unchanged.

## 0.2.0 — 2026-07-26

Panel-precursor release (PLAN-panel.md §11). Three additions, no physics
changes; the canonical scenarios and their acceptance tests are unaffected.

### Added

- **Manual trip actions** `trips.manual_mft` and `trips.manual_turbine` — the
  covered manual-trip pushbuttons every real control board carries. Effect is
  identical to the corresponding protective action by construction (both call
  the same `Simulator._do_mft` / `_do_turbine_trip`); the first-out record
  carries `MANUAL_MFT` / `MANUAL_TURBINE_TRIP` so a consumer can tell an
  operator-initiated trip from a protection-initiated one. Pressing a button
  whose trip is already latched is rejected-and-recorded, never raised. Manual
  trips carry no engine latch, so `trips.reset` clears them once the plant
  permits — the same convention as scenario-injected pump trips (D14).
- **Optional `label:` on protection-table entries** — 1-2 lines of at most 12
  characters, the engraved legend for an annunciator window; defaults to the
  bare id via `Condition.legend`. All 19 shipped conditions now carry one.
  Pure display data: the protection engine never reads it.

### Changed

- **Package-data migration (breaking for path-based consumers).**
  `configs/baseline.yaml`, `data/protection.yaml`, and `scenarios/*.yaml` moved
  into `src/hotwell/data/`, reachable through `importlib.resources`-backed
  accessors:

  | Accessor | Returns |
  |---|---|
  | `hotwell.data.baseline_config_path()` | traversable to the baseline config |
  | `hotwell.data.protection_table_path()` | traversable to the protection table |
  | `hotwell.data.builtin_scenarios()` | `{stem: traversable}` for the canonical scenarios |
  | `hotwell.data.read_text(resource)` | text of a packaged resource *or* a user path |

  `load_config()`, `load_protection_table()`, and `load_scenario()` all default
  to the packaged copies and still accept an explicit path override. `hotwell`
  therefore runs from any working directory with no repo checkout present —
  required by the panel (installed as a dependency) and by any PyPI release.

  Migration: replace `"scenarios/load_step.yaml"` with
  `hotwell.data.builtin_scenarios()["load_step"]`. `scripts/run_scenario.py`
  now takes a bare scenario name as well as a path.

  Removed constants: `hotwell.plant.DEFAULT_CONFIG`,
  `hotwell.protection.tables.DEFAULT_TABLE` (both were repo-root-relative).

### Notes

- `Simulator._do_mft` / `_do_turbine_trip` were extracted from
  `_apply_protective_actions` as a behavior-neutral refactor (verified: the
  37-test 0.1.0 suite passed unchanged before the manual-trip actions were
  added) so that "identical semantics" is structural rather than duplicated.

## 0.1.0 — 2026-07-26

Phase 1: headless deterministic steam-plant core. Two-state and Åström-Bell
drum models, three-element feedwater, protection/alarm engine with first-out,
sensor faults, historian, scenarios, mass/energy audit. See `HANDOFF.md`.
