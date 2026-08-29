# Changelog

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
