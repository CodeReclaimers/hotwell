"""Sensor models and the observation contract.

Pipeline per instrument (0.4.0, plan M3), in this order:

    truth -> lag (fault) -> + bias / drift (fault) -> + noise
          -> stuck override (fault) -> clamp to range -> quantize

Controllers and protection consume these sensed values, never truth.
At most one fault per instrument (a new sensor_fault event replaces the old).
Fault kinds (`SENSOR_FAULT_KINDS`):
  'stuck'           holds the previous step's sensed value
  'bias'            adds `bias` [instrument units]
  'drift'           adds rate * (t - t_start), magnitude capped at `max_bias`
  'lag'             first-order lag, time constant `tau_s` [s], applied to
                    truth from the moment the fault starts (no jump)
  'noise_increase'  multiplies the instrument's noise sigma by `factor`

Noise (config `sensors.noise.<instrument>: {sigma, tau}`, instrument units):
sigma = 0 is off. tau = 0 is white; tau > 0 is AR(1), the exact
discretisation of an Ornstein-Uhlenbeck process at dt,
    u_k = a u_{k-1} + sqrt(1 - a^2) z_k,  a = exp(-dt/tau),  noise = sigma u_k,
started in its stationary distribution (u_1 = z_1). Noise is added BEFORE
quantization on purpose: it dithers the rounding, which is otherwise a fixed
per-instrument bias of up to half an LSB.

Draw contract (plan invariant I2): when a SensorBank owns streams, every
instrument draws exactly one standard normal z_k from its own stream
`sensor.<instrument>` on every noisy sample, whatever its sigma, fault,
clamping or the plant state. A run with a fault and its fault-free twin
therefore see identical z sequences on every instrument. The init sample
(`noisy=False`) draws nothing.

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


#: kind -> required parameter names (scenario validation).
SENSOR_FAULT_KINDS: dict[str, tuple[str, ...]] = {
    "stuck": (),
    "bias": ("bias",),
    "drift": ("rate",),
    "lag": ("tau_s",),
    "noise_increase": ("factor",),
}


@dataclass
class SensorFault:
    """Active fault on one instrument (scenario-injected)."""

    kind: str          # one of SENSOR_FAULT_KINDS
    bias: float = 0.0  # additive offset [instrument units] for 'bias'
    t_start: float = 0.0
    t_end: float = float("inf")
    rate: float = 0.0              # 'drift' [instrument units / s]
    max_bias: float = float("inf")  # 'drift' magnitude cap [instrument units]
    tau_s: float = 0.0             # 'lag' time constant [s]
    factor: float = 1.0            # 'noise_increase' sigma multiplier [-]

    def __post_init__(self) -> None:
        if self.kind not in SENSOR_FAULT_KINDS:
            raise ValueError(f"unknown sensor fault kind {self.kind!r}")
        if self.kind == "lag" and not self.tau_s > 0.0:
            raise ValueError(f"lag fault needs tau_s > 0, got {self.tau_s}")
        if self.kind == "noise_increase" and not self.factor >= 0.0:
            raise ValueError(f"noise_increase needs factor >= 0, got {self.factor}")
        if not self.max_bias >= 0.0:
            raise ValueError(f"max_bias must be >= 0, got {self.max_bias}")


@dataclass(frozen=True)
class NoiseSpec:
    """Noise on one instrument: stationary sigma [instrument units], AR(1)
    correlation time tau [s] (0 = white)."""

    sigma: float = 0.0
    tau: float = 0.0


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
    ``1``/``0`` and strings as UTF-8, then the separator ``#``, then each
    non-clear alarm in the order given (protection-table order) as
    ``id=state\\0``. That includes the acknowledgement state. `plant_dead` is
    not included.
    """
    out = np.array([obs.values[s.name] for s in OBSERVATION_SPEC],
                   dtype=np.float64).tobytes()
    parts = [out]
    for k in sorted(obs.indications):
        v = obs.indications[k]
        enc = (b"1" if v else b"0") if isinstance(v, bool) else str(v).encode()
        parts.append(k.encode() + b"=" + enc + b"\x00")
    parts.append(b"#")
    for aid, state in obs.alarms:
        parts.append(aid.encode() + b"=" + state.encode() + b"\x00")
    return b"".join(parts)


class SensorBank:
    """Applies the sensing pipeline to a truth dict."""

    #: draws buffered per stream refill. A block of n draws is the same
    #: sequence as n single draws (tests/test_m3_sensors.py checks this).
    BLOCK = 4096

    def __init__(self, noise: dict | None = None, streams=None,
                 dt: float = 0.05) -> None:
        self.spec = {s.name: s for s in OBSERVATION_SPEC}
        self.names = [s.name for s in OBSERVATION_SPEC]
        self.faults: dict[str, SensorFault] = {}
        self._last: dict[str, float] = {}
        self._lag: dict[str, float] = {}
        self.dt = dt
        noise = noise or {}
        unknown = set(noise) - set(self.spec)
        if unknown:
            raise ValueError(f"sensors.noise names unknown instruments: {sorted(unknown)}")
        self.noise = {n: NoiseSpec(**noise.get(n, {})) for n in self.names}
        for n, ns in self.noise.items():
            if ns.sigma < 0.0 or ns.tau < 0.0:
                raise ValueError(f"sensors.noise.{n}: sigma and tau must be >= 0")
        self._a = np.array([np.exp(-dt / self.noise[n].tau) if self.noise[n].tau > 0.0
                            else 0.0 for n in self.names])
        self._b = np.sqrt(1.0 - self._a * self._a)
        self._sigma = np.array([self.noise[n].sigma for n in self.names])
        self._gens = ([streams.stream(f"sensor.{n}") for n in self.names]
                      if streams is not None else None)
        self._buf = np.empty((len(self.names), 0))
        self._j = 0
        self._u: np.ndarray | None = None       # unit AR(1) state, None before 1st draw
        #: this step's raw standard-normal draws, in OBSERVATION_SPEC order
        #: (None until the first noisy sample). Exposed for the I2 twin test.
        self.last_draws: np.ndarray | None = None

    def _draw(self) -> np.ndarray:
        if self._j >= self._buf.shape[1]:
            self._buf = np.stack([g.normal(size=self.BLOCK) for g in self._gens])
            self._j = 0
        z = self._buf[:, self._j]
        self._j += 1
        return z

    def sample(self, t: float, truth: dict[str, float],
               noisy: bool = True) -> dict[str, float]:
        """truth -> lag -> bias/drift -> noise -> stuck -> clamp -> quantize."""
        noise_vec = None
        if noisy and self._gens is not None:
            z = self._draw()                      # always, for every instrument (I2)
            self._u = z.copy() if self._u is None else self._a * self._u + self._b * z
            self.last_draws = z.copy()
            noise_vec = self._u
        out: dict[str, float] = {}
        for i, name in enumerate(self.names):
            s = self.spec[name]
            v = truth[name]
            f = self.faults.get(name)
            active = f is not None and f.t_start <= t < f.t_end
            if not active:
                self._lag.pop(name, None)
            if active and f.kind == "lag":
                prev = self._lag.get(name, v)
                v = prev + (1.0 - np.exp(-self.dt / f.tau_s)) * (v - prev)
                self._lag[name] = v
            elif active and f.kind == "bias":
                v = v + f.bias
            elif active and f.kind == "drift":
                d = f.rate * (t - f.t_start)
                v = v + max(-f.max_bias, min(f.max_bias, d))
            if noise_vec is not None:
                sig = self._sigma[i]
                if active and f.kind == "noise_increase":
                    sig = sig * f.factor
                if sig != 0.0:
                    v = v + sig * float(noise_vec[i])
            if active and f.kind == "stuck":
                v = self._last.get(name, v)
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
