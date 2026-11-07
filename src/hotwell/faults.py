"""Hidden physical faults (0.4.0, plan M5).

Each fault is a scenario event that sets a multiplicative factor (or a stuck
flag) in `Discrete`. Like every discrete quantity it is frozen during the RK4
stages and changes only at step boundaries. With optional `ramp_s`, a factor
moves linearly from its current value to the target over round(ramp_s/dt)
steps with an exact endpoint, the same rule as load ramps. All factors
default to 1.0, and x * 1.0 is exact in IEEE arithmetic, so a zero-magnitude
fault is bit-identical to no fault.

Events (params; effect):
  pump_degrade       target cp1|cp2|fp1|fp2, head_factor > 0; shutoff head H0*f
  valve_degrade      target frv|lcv, cv_factor > 0; valve Cv*f (plug < 1, erosion > 1)
  actuator_stuck     target fw_valve|throttle|firing|da_lcv, optional t_end; frozen
  actuator_slow      target fw_valve|throttle|firing, rate_factor > 0; slew limit * f
  firing_degrade     eta_factor > 0; combustion efficiency * f
  condenser_fouling  slope_factor > 0; load-dependent p_cond term * f
All factor faults take optional ramp_s.

A stuck actuator's position stays where it was; the controller's output keeps
moving (in `Simulator.control`, i.e. the panel's loop readout), and that
divergence is the operator's clue. The position instrument is truthful. The
DA level-control valve has no actuator state (its position IS the
controller command), so "stuck da_lcv" holds the command value instead.
Trip slams (MFT on firing, turbine trip on throttle) still act; they model the
separate trip valves (D12).
"""
from __future__ import annotations

from dataclasses import dataclass

#: event type -> (Discrete attribute, allowed targets or None, factor param name)
FACTOR_FAULTS: dict[str, tuple[str, tuple[str, ...] | None, str]] = {
    "pump_degrade": ("head_factor", ("cp1", "cp2", "fp1", "fp2"), "head_factor"),
    "valve_degrade": ("cv_factor", ("frv", "lcv"), "cv_factor"),
    "actuator_slow": ("rate_factor", ("fw_valve", "throttle", "firing"), "rate_factor"),
    "firing_degrade": ("eta_factor", None, "eta_factor"),
    "condenser_fouling": ("fouling_factor", None, "slope_factor"),
}
STUCK_TARGETS = ("fw_valve", "throttle", "firing", "da_lcv")
PLANT_FAULT_TYPES = frozenset(FACTOR_FAULTS) | {"actuator_stuck"}


def check_plant_fault(scenario: str, etype: str, p: dict) -> None:
    """Load-time validation (raises ValueError)."""
    where = f"{scenario}: {etype}"
    if etype == "actuator_stuck":
        if p.get("target") not in STUCK_TARGETS:
            raise ValueError(f"{where}: target must be one of {STUCK_TARGETS}, "
                             f"got {p.get('target')!r}")
        return
    _attr, targets, pname = FACTOR_FAULTS[etype]
    if targets is not None and p.get("target") not in targets:
        raise ValueError(f"{where}: target must be one of {targets}, got {p.get('target')!r}")
    if pname not in p:
        raise ValueError(f"{where}: missing {pname!r}")
    if not float(p[pname]) > 0.0:
        raise ValueError(f"{where}: {pname} must be > 0, got {p[pname]}")
    if float(p.get("ramp_s", 0.0)) < 0.0:
        raise ValueError(f"{where}: ramp_s must be >= 0")


@dataclass
class _Ramp:
    attr: str
    key: str | None
    v_start: float
    v_end: float
    k: int
    n: int


class FaultDriver:
    """Applies plant-fault events to `Discrete` and advances their ramps."""

    def __init__(self, disc, dt: float) -> None:
        self.disc = disc
        self.dt = dt
        self.ramps: dict[tuple[str, str | None], _Ramp] = {}
        self._unstick: dict[str, float] = {}   # target -> t_end

    def _get(self, attr: str, key: str | None) -> float:
        v = getattr(self.disc, attr)
        return v[key] if key is not None else v

    def _set(self, attr: str, key: str | None, value: float) -> None:
        if key is None:
            setattr(self.disc, attr, value)
        else:
            getattr(self.disc, attr)[key] = value

    def apply(self, etype: str, p: dict, t: float, lcv_cmd: float) -> None:
        """Apply one event at step-start time t. `lcv_cmd` is the current DA
        LCV command (held if da_lcv sticks)."""
        if etype == "actuator_stuck":
            tgt = p["target"]
            self.disc.stuck[tgt] = lcv_cmd if tgt == "da_lcv" else 0.0
            if "t_end" in p:
                self._unstick[tgt] = float(p["t_end"])
            return
        attr, _targets, pname = FACTOR_FAULTS[etype]
        key = p.get("target") if _targets is not None else None
        target = float(p[pname])
        ramp_s = float(p.get("ramp_s", 0.0))
        self.ramps.pop((attr, key), None)
        if ramp_s <= 0.0:
            self._set(attr, key, target)
        else:
            n = max(1, int(round(ramp_s / self.dt)))
            self.ramps[(attr, key)] = _Ramp(attr, key, self._get(attr, key), target, 0, n)

    def advance(self, t: float) -> None:
        """Once per step: release expired stuck actuators, move ramps one step."""
        for tgt, t_end in list(self._unstick.items()):
            if t >= t_end - 1e-9:
                self.disc.stuck.pop(tgt, None)
                del self._unstick[tgt]
        for k in list(self.ramps):
            r = self.ramps[k]
            r.k += 1
            if r.k >= r.n:
                self._set(r.attr, r.key, r.v_end)
                del self.ramps[k]
            else:
                self._set(r.attr, r.key, r.v_start + (r.v_end - r.v_start) * (r.k / r.n))
