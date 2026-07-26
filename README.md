# hotwell

Headless reduced-order simulation core for a small (60 MW, fictional) saturated-steam
power plant — phase 1 of a browser-based plant simulator with a 1970s-style control
panel and an AI operator-assistance agent. This package is the physics/control/protection
library only: no server, no UI, no agent.

- Fixed-step classical RK4 at 20 Hz; slow storage as ODE states, pressure/flow network
  solved algebraically inside the derivative.
- Deterministic: seed + scenario ⇒ bit-identical trajectories.
- SI units internally (Pa, kg, kg/s, J, K, W, rad/s).
- Contracts for the later phases: observation spec, action schema, scenario files,
  data-driven protection tables (`data/protection.yaml`).

## Install (development)

```bash
uv venv .venv
uv pip install -e '.[dev]'
```

Runtime dependencies are numpy, scipy, pyyaml only. matplotlib is a dev dependency used
by `scripts/` and is never imported by the package.

## Test

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

## Run a scenario

```bash
.venv/bin/python scripts/run_scenario.py scenarios/cp1_trip_unrecovered.yaml --plots out/
```

## Regenerate steam property fits

```bash
.venv/bin/python scripts/gen_steam_props.py
```

Provenance and accuracy report are embedded in the generated
`src/hotwell/steam_properties.py`.

See `PLAN-sim-core.md` for the full phase-1 specification and `HANDOFF.md` for current
status, achieved design-point values, and open questions.
