"""Named, independent random streams (0.4.0, plan M1, invariant I2).

Every stochastic consumer draws from its own `numpy.random.Generator`, seeded
by ``SeedSequence([seed, STREAM_IDS[name]])``. Two consequences:

- Adding a consumer, or changing how much one consumer draws, never shifts any
  other consumer's sequence.
- A run with a fault and its fault-free twin share identical realizations on
  every stream, provided each consumer draws a fixed count per step whatever
  the plant state is (the consumers' contract, enforced where they are built).

`STREAM_IDS` is **append-only**: an ID, once assigned, never changes or gets
reused, or every recorded run that used it stops reproducing.
`tests/test_rng.py` pins the table. The IDs are written out literally, not
derived from `OBSERVATION_SPEC` order, so reordering the instrument list can't
renumber streams.

Determinism scope: bit-identical for the same seed, scenario, platform and
**numpy version**. NumPy keeps the `SeedSequence`/PCG64 bit streams stable,
but it does not promise that `Generator` distribution methods (e.g. `normal`)
stay the same across releases; `tests/test_rng.py` pins raw draws so that a
change is caught loudly rather than as a silent hash break.
"""
from __future__ import annotations

from types import MappingProxyType

import numpy as np

_IDS: dict[str, int] = {
    # 1000-series: per-instrument sensor noise (plan M3). One stream per
    # instrument so a fault on one instrument cannot perturb another's noise.
    "sensor.drum_pressure": 1000,
    "sensor.drum_level": 1001,
    "sensor.steam_flow": 1002,
    "sensor.feed_flow": 1003,
    "sensor.condensate_flow": 1004,
    "sensor.chest_pressure": 1005,
    "sensor.cond_pressure": 1006,
    "sensor.hotwell_level": 1007,
    "sensor.da_level": 1008,
    "sensor.da_pressure": 1009,
    "sensor.frequency": 1010,
    "sensor.mw_out": 1011,
    "sensor.cp1_current": 1012,
    "sensor.cp2_current": 1013,
    "sensor.fp1_current": 1014,
    "sensor.fp2_current": 1015,
    "sensor.fw_valve_pos": 1016,
    "sensor.throttle_pos": 1017,
    "sensor.firing_rate": 1018,
    "sensor.da_lcv_pos": 1019,
    "sensor.fp1_npsh_margin": 1020,
    "sensor.fp2_npsh_margin": 1021,
    # 0.4.0 M5b (appended)
    "sensor.makeup_flow": 1022,
    "sensor.makeup_valve_pos": 1023,
    "sensor.cp1_npsh_margin": 1024,
    "sensor.cp2_npsh_margin": 1025,
    # 2000-series: load process noise (plan M4).
    "load.vital": 2000,
    "load.nonvital": 2001,
    # 3000-series: background-operator timing (plan M6).
    "operator": 3000,
}

#: Read-only view of the stream-name -> ID table. Append-only (see module doc).
STREAM_IDS = MappingProxyType(_IDS)


class StreamBank:
    """Lazily created, cached generators, one per registered stream name."""

    def __init__(self, seed: int) -> None:
        seed = int(seed)
        if seed < 0:
            raise ValueError(f"seed must be non-negative, got {seed}")
        self.seed = seed
        self._streams: dict[str, np.random.Generator] = {}

    def stream(self, name: str) -> np.random.Generator:
        """The generator for `name`; the same object on every call, so draws
        consume one persistent sequence. Unknown names raise KeyError."""
        g = self._streams.get(name)
        if g is None:
            if name not in STREAM_IDS:
                raise KeyError(f"unknown rng stream {name!r}: register it in "
                               "hotwell.rng.STREAM_IDS (append-only)")
            g = np.random.default_rng(
                np.random.SeedSequence([self.seed, STREAM_IDS[name]]))
            self._streams[name] = g
        return g
