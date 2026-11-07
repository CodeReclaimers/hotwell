"""Actuators (first-order lag + rate/travel limits) and liquid valve flow law.

Positions are continuous states in [0, 1]; commands come from controllers or
manual-mode actions and are frozen during RK4 stages. Travel limits are
enforced by the derivative shape plus a post-step clamp in the event layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from hotwell.state import StateRegistry


@dataclass(frozen=True)
class ActuatorParams:
    tau: float   # first-order time constant [s]
    rate: float  # max |dx/dt| [1/s]


class Actuator:
    """First-order position lag: dx/dt = clip((cmd - x)/tau, -rate, +rate)."""

    def __init__(self, name: str, params: ActuatorParams, reg: StateRegistry,
                 initial: float = 0.0) -> None:
        self.name = name
        self.p = params
        self.i_x = reg.register(f"{name}.x", initial, "-", 1.0)

    def deriv(self, y: list[float], ydot: list[float], cmd: float,
              stuck: bool = False, rate_factor: float = 1.0) -> None:
        """0.4.0 M5: `stuck` freezes the position (zero derivative);
        `rate_factor` scales the slew limit (a sticky positioner)."""
        if stuck:
            ydot[self.i_x] = 0.0
            return
        cmd = 0.0 if cmd < 0.0 else (1.0 if cmd > 1.0 else cmd)
        r = (cmd - y[self.i_x]) / self.p.tau
        rate = self.p.rate * rate_factor
        ydot[self.i_x] = -rate if r < -rate else (rate if r > rate else r)


def valve_flow(cv: float, x: float, dp: float) -> float:
    """Liquid valve mass flow [kg/s]: m = Cv * x * sqrt(max(dp, 0)).

    cv [kg/(s*Pa^0.5)], x position [-], dp pressure drop [Pa].
    """
    if dp <= 0.0 or x <= 0.0:
        return 0.0
    return cv * x * sqrt(dp)


def valve_dp(cv: float, x: float, m_dot: float) -> float:
    """Pressure drop [Pa] across a liquid valve passing m_dot [kg/s].

    Inverse of valve_flow; x is floored at 1e-4 so a shut valve reads as a
    very large (not infinite) resistance in the network solve.
    """
    x_eff = x if x > 1e-4 else 1e-4
    r = m_dot / (cv * x_eff)
    return r * r
