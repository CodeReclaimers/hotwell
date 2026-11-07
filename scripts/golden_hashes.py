"""Independent golden-hash computation (0.4.0 M0 gate).

Usage:
    python scripts/golden_hashes.py [HOTWELL_SRC_DIR]

With no argument, uses the installed hotwell. With a src dir (e.g. a pristine
`git worktree add --detach /tmp/hw 9464eb2` checkout's src/), imports hotwell
from there and asserts it did. The goldens in tests/test_golden_hashes.py were
produced this way against 9464eb2 (hotwell 0.3.0).

Runs each canonical
scenario under both fidelities with Simulator.run(), and prints:
  - the simulator's own state-history hash (sim.state_history_hash)
  - an observation hash computed HERE, outside the simulator, from the
    Observation objects step() returns, using the M0 encoding:
      per step: float64 bytes of values in OBSERVATION_SPEC order, then for
      each indication in sorted-key order: key, b'=', b'1'/b'0' (bool) or
      the UTF-8 str, b'\\x00'; then b'#'; then each alarm (id, state) in the
      order Observation.alarms gives (table order) as id, b'=', state, b'\\x00'.
"""
import hashlib
import sys
import time
from pathlib import Path

src = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
if src is not None:
    sys.path.insert(0, str(src))

import numpy as np  # noqa: E402

import hotwell  # noqa: E402
from hotwell import data  # noqa: E402
from hotwell.plant import load_config  # noqa: E402
from hotwell.scenario import load_scenario  # noqa: E402
from hotwell.sensors import OBSERVATION_SPEC  # noqa: E402
from hotwell.simulator import Simulator  # noqa: E402

if src is not None:
    assert Path(hotwell.__file__).resolve().is_relative_to(src), hotwell.__file__
print(f"hotwell from {hotwell.__file__}", flush=True)

FIDELITIES = {
    "two_state_1e": ("two_state", False),
    "astrom_bell_3e": ("astrom_bell", True),
}
SCENARIOS = ("cp1_trip_unrecovered", "cp1_trip_recovered", "load_step")
NAMES = [s.name for s in OBSERVATION_SPEC]


def obs_bytes(obs) -> bytes:
    out = np.array([obs.values[n] for n in NAMES], dtype=np.float64).tobytes()
    for k in sorted(obs.indications):
        v = obs.indications[k]
        enc = (b"1" if v else b"0") if isinstance(v, bool) else str(v).encode()
        out += k.encode() + b"=" + enc + b"\x00"
    out += b"#"
    for aid, state in obs.alarms:
        out += f"{aid}={state}".encode() + b"\x00"
    return out


for fid, (model, te) in FIDELITIES.items():
    for name in SCENARIOS:
        t0 = time.perf_counter()
        cfg = load_config()
        cfg["drum"]["model"] = model
        cfg["control"]["drum_level"]["three_element"] = te
        sc = load_scenario(data.builtin_scenarios()[name])
        sim = Simulator(cfg, scenario=sc)
        sim.initialize_steady_state(sc.load_mw)
        h = hashlib.sha256()
        steps = 0
        while sim.t < sc.max_t - 0.5 * sim.dt:
            obs = sim.step()
            h.update(obs_bytes(obs))
            steps += 1
            if obs.plant_dead:
                break
        print(f"{fid:15s} {name:22s} steps={steps:6d} t={sim.t:8.2f} "
              f"dead={sim.disc.plant_dead!s:5s} "
              f"state={sim.state_history_hash} obs={h.hexdigest()} "
              f"({time.perf_counter() - t0:.1f} s)", flush=True)
