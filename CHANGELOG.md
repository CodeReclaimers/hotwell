# Changelog

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
