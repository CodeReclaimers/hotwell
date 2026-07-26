"""Electrical load blocks on the islanded bus.

Each block: P = P0 * (1 + k_pf * (omega - omega0)/omega0) [W].
Vital is connected while the bus is alive; non-vital is connectable/sheddable
by action or underfrequency protection. The generator breaker (opened by a
turbine trip) deenergizes the whole bus.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LoadBlock:
    """One load block; p0 is mutable (scenario load steps)."""

    name: str
    p0: float    # rated power at nominal frequency [W]
    k_pf: float  # frequency dependence [-]

    def power(self, omega: float, omega0: float) -> float:
        """Electrical demand [W] at rotor speed omega [rad/s]."""
        return self.p0 * (1.0 + self.k_pf * (omega - omega0) / omega0)


class Loads:
    """Vital + non-vital blocks; connection state lives in Discrete."""

    def __init__(self, vital: LoadBlock, nonvital: LoadBlock) -> None:
        self.vital = vital
        self.nonvital = nonvital

    def p_elec(self, omega: float, omega0: float, nonvital_connected: bool,
               breaker_closed: bool) -> float:
        """Total electrical load on the generator [W]."""
        if not breaker_closed:
            return 0.0
        p = self.vital.power(omega, omega0)
        if nonvital_connected:
            p += self.nonvital.power(omega, omega0)
        return p
