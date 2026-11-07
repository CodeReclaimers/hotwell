"""Sensor models and the observation contract.

Pipeline per instrument: truth -> optional active fault -> clamp to range ->
quantize to display resolution. Controllers and protection consume these
sensed values, never truth. Fault modes (M2): 'stuck' holds the last sensed
value; 'bias' adds an offset before clamping.

The instrument list below is the observation contract for the later panel
and agent phases; keep it boring and explicit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class InstrumentSpec:
    """One instrument: name, SI units, range, display resolution, description."""

    name: str
    units: str
    lo: float
    hi: float
    resolution: float
    description: str


# The phase-1 instrument list (plan section 8.1). All SI.
OBSERVATION_SPEC: tuple[InstrumentSpec, ...] = (
    InstrumentSpec("drum_pressure", "Pa", 0.0, 12.0e6, 1.0e4, "drum pressure"),
    InstrumentSpec("drum_level", "m", -0.5, 0.5, 1.0e-3, "drum level rel. NWL"),
    InstrumentSpec("steam_flow", "kg/s", 0.0, 150.0, 0.1, "main steam (throttle) flow"),
    InstrumentSpec("feed_flow", "kg/s", 0.0, 150.0, 0.1, "feedwater flow to drum"),
    InstrumentSpec("condensate_flow", "kg/s", 0.0, 150.0, 0.1, "condensate flow to DA"),
    InstrumentSpec("chest_pressure", "Pa", 0.0, 12.0e6, 1.0e4, "turbine steam chest pressure"),
    InstrumentSpec("cond_pressure", "Pa", 0.0, 20.0e3, 50.0, "condenser pressure"),
    InstrumentSpec("hotwell_level", "m", -1.0, 1.5, 1.0e-3, "hotwell level rel. nominal"),
    InstrumentSpec("da_level", "m", -2.5, 0.5, 1.0e-3, "deaerator level rel. nominal"),
    InstrumentSpec("da_pressure", "Pa", 0.0, 0.3e6, 1.0e3, "deaerator pressure"),
    InstrumentSpec("frequency", "Hz", 50.0, 70.0, 0.01, "bus/rotor frequency"),
    InstrumentSpec("mw_out", "W", 0.0, 80.0e6, 1.0e5, "generator electrical output"),
    InstrumentSpec("cp1_current", "A", 0.0, 100.0, 0.5, "CP-1 motor current (proxy)"),
    InstrumentSpec("cp2_current", "A", 0.0, 100.0, 0.5, "CP-2 motor current (proxy)"),
    InstrumentSpec("fp1_current", "A", 0.0, 500.0, 1.0, "FP-1 motor current (proxy)"),
    InstrumentSpec("fp2_current", "A", 0.0, 500.0, 1.0, "FP-2 motor current (proxy)"),
    InstrumentSpec("fw_valve_pos", "-", 0.0, 1.0, 0.005, "feed reg valve position"),
    InstrumentSpec("throttle_pos", "-", 0.0, 1.0, 0.005, "throttle valve position"),
    InstrumentSpec("firing_rate", "-", 0.0, 1.0, 0.005, "firing rate fraction"),
    InstrumentSpec("da_lcv_pos", "-", 0.0, 1.0, 0.005, "DA level control valve position"),
    InstrumentSpec("fp1_npsh_margin", "m", -5.0, 15.0, 0.05, "FP-1 NPSH margin"),
    InstrumentSpec("fp2_npsh_margin", "m", -5.0, 15.0, 0.05, "FP-2 NPSH margin"),
)


@dataclass
class SensorFault:
    """Active fault on one instrument (scenario-injected)."""

    kind: str          # 'stuck' | 'bias'
    bias: float = 0.0  # additive offset [instrument units] for 'bias'
    t_start: float = 0.0
    t_end: float = float("inf")


@dataclass
class Observation:
    """What the panel/agent/controllers see each step."""

    t: float
    values: dict[str, float]
    alarms: list[tuple[str, str]]          # (alarm id, state) — active/acknowledged
    indications: dict[str, bool | str]     # run lights, breaker/trip flags (honest)
    plant_dead: bool = False


def observation_bytes(obs: Observation) -> bytes:
    """Canonical byte encoding of one observation (0.4.0, M0).

    Feeds `Simulator.observation_hash`; public so external consumers (the
    bench repo's dump exporter) can hash what they export the same way.
    Encoding: the sensed values as float64 in `OBSERVATION_SPEC` order, then
    each indication in sorted-key order as ``key=value\\0`` with bools as
    ``1``/``0`` and strings as UTF-8. Alarms and `plant_dead` are not included.
    """
    out = np.array([obs.values[s.name] for s in OBSERVATION_SPEC],
                   dtype=np.float64).tobytes()
    parts = [out]
    for k in sorted(obs.indications):
        v = obs.indications[k]
        enc = (b"1" if v else b"0") if isinstance(v, bool) else str(v).encode()
        parts.append(k.encode() + b"=" + enc + b"\x00")
    return b"".join(parts)


class SensorBank:
    """Applies the sensing pipeline to a truth dict."""

    def __init__(self) -> None:
        self.spec = {s.name: s for s in OBSERVATION_SPEC}
        self.faults: dict[str, SensorFault] = {}
        self._last: dict[str, float] = {}

    def sample(self, t: float, truth: dict[str, float]) -> dict[str, float]:
        """truth -> fault -> clamp -> quantize, for every instrument."""
        out: dict[str, float] = {}
        for name, s in self.spec.items():
            v = truth[name]
            f = self.faults.get(name)
            if f is not None and f.t_start <= t < f.t_end:
                if f.kind == "stuck":
                    v = self._last.get(name, v)
                elif f.kind == "bias":
                    v = v + f.bias
            if v < s.lo:
                v = s.lo
            elif v > s.hi:
                v = s.hi
            v = round(v / s.resolution) * s.resolution
            out[name] = v
        self._last = out
        return out


@dataclass
class RejectedAction:
    """Record of an invalid action (never raises mid-run)."""

    t: float
    action: dict = field(default_factory=dict)
    reason: str = ""
