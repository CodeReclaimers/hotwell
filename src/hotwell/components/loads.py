"""Electrical load blocks on the islanded bus.

Each block: P = P0 * (1 + k_pf * (omega - omega0)/omega0) [W].
Vital is connected while the bus is alive; non-vital is connectable/sheddable
by action or underfrequency protection. The generator breaker (opened by a
turbine trip) deenergizes the whole bus.

Station service (0.3.0): running pump motors also load the bus. Their draw is
computed by the plant from the solved hydraulics and passed in per evaluation;
it is frequency-independent, consistent with the pump model whose shaft speed
does not track bus frequency.

Load schedule and process noise (0.4.0, plan M4) live in `LoadDriver`:
- `set_load(..., ramp_s)` ramps the block's scheduled `p0` linearly over
  round(ramp_s/dt) steps (exact endpoint), evaluated at step boundaries,
  so `p0` is frozen during the RK4 stages like all discrete state.
- Process noise: `p_dev = sigma_w * u`, with u a unit-variance OU process
  (exact AR(1) at dt, correlation time tau > 0) on stream `load.<block>`.
  It **starts at u = 0** (not stationary) because a stationary start would
  be a physical step of size sigma_w*z at t = 0+ on a plant just initialised
  at equilibrium; u relaxes to its stationary spread within a few tau.
  Each block draws exactly one normal per step whatever its sigma,
  connection state or the plant state (plan invariant I2).
The demand is (p0 + p_dev), floored at 0, times the frequency factor.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, sqrt

BLOCK_NAMES = ("vital", "nonvital")


@dataclass
class LoadBlock:
    """One load block; p0 is mutable (scenario load steps)."""

    name: str
    p0: float    # scheduled power at nominal frequency [W]
    k_pf: float  # frequency dependence [-]
    p_dev: float = 0.0  # process-noise deviation from the schedule [W] (0.4.0)

    def power(self, omega: float, omega0: float) -> float:
        """Electrical demand [W] at rotor speed omega [rad/s]."""
        p = self.p0 + self.p_dev
        if p < 0.0:
            p = 0.0
        return p * (1.0 + self.k_pf * (omega - omega0) / omega0)


class Loads:
    """Vital + non-vital blocks; connection state lives in Discrete."""

    def __init__(self, vital: LoadBlock, nonvital: LoadBlock) -> None:
        self.vital = vital
        self.nonvital = nonvital

    def p_elec(self, omega: float, omega0: float, nonvital_connected: bool,
               breaker_closed: bool, station_service: float = 0.0) -> float:
        """Total electrical load on the generator [W], station service
        (running pump motors) included. A dead bus carries nothing."""
        if not breaker_closed:
            return 0.0
        p = self.vital.power(omega, omega0) + station_service
        if nonvital_connected:
            p += self.nonvital.power(omega, omega0)
        return p


@dataclass
class _Ramp:
    p_start: float  # [W]
    p_end: float    # [W]
    k: int          # steps taken
    n: int          # steps in the ramp


class LoadDriver:
    """Advances load-block schedules (ramps) and process noise once per step."""

    def __init__(self, loads: Loads, noise: dict | None, streams, dt: float) -> None:
        self.blocks = {"vital": loads.vital, "nonvital": loads.nonvital}
        self.dt = dt
        noise = noise or {}
        unknown = set(noise) - set(BLOCK_NAMES)
        if unknown:
            raise ValueError(f"loads.noise names unknown blocks: {sorted(unknown)}")
        self.sigma: dict[str, float] = {}
        self._a: dict[str, float] = {}
        self._b: dict[str, float] = {}
        for b in BLOCK_NAMES:
            cfg = noise.get(b, {})
            sigma, tau = float(cfg.get("sigma_w", 0.0)), float(cfg.get("tau", 0.0))
            if sigma < 0.0 or tau < 0.0:
                raise ValueError(f"loads.noise.{b}: sigma_w and tau must be >= 0")
            if sigma > 0.0 and tau == 0.0:
                raise ValueError(f"loads.noise.{b}: sigma_w > 0 needs tau > 0 "
                                 "(white load noise at 20 Hz is unphysical)")
            self.sigma[b] = sigma
            self._a[b] = exp(-dt / tau) if tau > 0.0 else 0.0
            self._b[b] = sqrt(1.0 - self._a[b] ** 2)
        self._u = {b: 0.0 for b in BLOCK_NAMES}
        self._gens = ({b: streams.stream(f"load.{b}") for b in BLOCK_NAMES}
                      if streams is not None else None)
        self.ramps: dict[str, _Ramp] = {}
        #: this step's raw draws {block: z} (I2 twin tests); None before step 1.
        self.last_draws: dict[str, float] | None = None

    def set_load(self, target: str, p0: float, ramp_s: float = 0.0) -> None:
        """Step (ramp_s = 0) or ramp the scheduled p0 [W]. Replaces any active
        ramp on that block; a ramp starts from the block's current p0."""
        block = self.blocks[target]
        self.ramps.pop(target, None)
        if ramp_s <= 0.0:
            block.p0 = p0
        else:
            n = max(1, int(round(ramp_s / self.dt)))
            self.ramps[target] = _Ramp(block.p0, p0, 0, n)

    def advance(self) -> None:
        """One step: move active ramps one increment, then draw the noise."""
        for name in list(self.ramps):
            r = self.ramps[name]
            r.k += 1
            if r.k >= r.n:
                self.blocks[name].p0 = r.p_end
                del self.ramps[name]
            else:
                self.blocks[name].p0 = r.p_start + (r.p_end - r.p_start) * (r.k / r.n)
        if self._gens is None:
            return
        draws = {}
        for b in BLOCK_NAMES:                     # fixed order, always (I2)
            z = float(self._gens[b].normal())
            draws[b] = z
            self._u[b] = self._a[b] * self._u[b] + self._b[b] * z
            if self.sigma[b] != 0.0:
                self.blocks[b].p_dev = self.sigma[b] * self._u[b]
        self.last_draws = draws
