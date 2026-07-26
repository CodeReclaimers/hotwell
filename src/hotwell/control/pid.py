"""Discrete-time PI controller with output limits and back-calculation anti-windup.

Runs at the simulation step rate (20 Hz). No derivative term (plan section 6).
Each controller has auto | manual mode; in manual the operator command passes
through and the integrator tracks for bumpless return to auto.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PIParams:
    kp: float      # proportional gain [output units / PV units]
    ki: float      # integral gain [output units / (PV units * s)]
    lo: float      # output low limit
    hi: float      # output high limit
    t_track: float  # anti-windup tracking time [s]


class PI:
    """One PI loop. update() implements:

    u_raw = kp*e + I;  u = clamp(u_raw);  I += (ki*e + (u - u_raw)/t_track)*dt
    """

    def __init__(self, params: PIParams, sp: float) -> None:
        self.p = params
        self.sp = sp            # setpoint [PV units]
        self.integ = 0.0        # integrator state [output units]
        self.mode = "auto"      # "auto" | "manual"
        self.manual_cmd = 0.0   # manual output [output units]
        self.output = 0.0       # last output

    def initialize(self, output: float, pv: float) -> None:
        """Bumpless start: integrator set so current output holds at current PV."""
        e = self.sp - pv
        self.integ = output - self.p.kp * e
        self.output = output
        self.manual_cmd = output

    def update(self, pv: float, dt: float) -> float:
        """Advance one step against measured pv; returns actuator command."""
        e = self.sp - pv
        if self.mode == "manual":
            u = self.manual_cmd
            if u < self.p.lo:
                u = self.p.lo
            elif u > self.p.hi:
                u = self.p.hi
            # track so a return to auto is bumpless
            self.integ = u - self.p.kp * e
            self.output = u
            return u
        u_raw = self.p.kp * e + self.integ
        u = u_raw
        if u < self.p.lo:
            u = self.p.lo
        elif u > self.p.hi:
            u = self.p.hi
        self.integ += (self.p.ki * e + (u - u_raw) / self.p.t_track) * dt
        self.output = u
        return u
