"""Turbine: throttle flow law, steam chest lag, mechanical power, rotor swing.

Throttle (choked approximation): m_throttle = k_t * x * p_drum [kg/s].
Steam chest: tau_ch * dp_chest/dt = x * p_drum - p_chest — a first-order lag
between valve-commanded flow and mechanical power. Turbine through-flow
(= exhaust to condenser) is k_t * p_chest, so transient chest storage is
exactly k_t * tau_ch * p_chest [kg] (counted in the mass audit).

Swing (islanded): J * domega/dt = (P_m - P_e)/omega - D_m*(omega - omega0).
"""
from __future__ import annotations

from dataclasses import dataclass

from hotwell.state import StateRegistry


@dataclass(frozen=True)
class TurbineParams:
    k_t: float       # throttle flow coefficient [kg/(s*Pa)]
    w_spec: float    # specific work [J/kg]
    tau_chest: float  # chest lag [s]
    x_rated: float   # throttle position at rated flow/pressure [-]


@dataclass(frozen=True)
class RotorParams:
    s_rating: float  # generator rating [VA]
    h_inertia: float  # inertia constant [s]
    d_m: float       # mechanical damping [N*m*s/rad]
    f0: float        # rated frequency [Hz]

    @property
    def omega0(self) -> float:
        """Rated speed [rad/s] (2-pole equivalent)."""
        return 6.283185307179586 * self.f0

    @property
    def j_inertia(self) -> float:
        """Rotational inertia J = 2*H*S/omega0^2 [kg*m^2]."""
        w0 = self.omega0
        return 2.0 * self.h_inertia * self.s_rating / (w0 * w0)


class Turbine:
    """Steam chest + rotor states; algebraic flow/power helpers."""

    def __init__(self, tp: TurbineParams, rp: RotorParams, reg: StateRegistry) -> None:
        self.tp = tp
        self.rp = rp
        self.i_pch = reg.register("chest.p", 6.8e6, "Pa", 8.0e6)
        self.i_omega = reg.register("rotor.omega", rp.omega0, "rad/s", 40.0)
        self._j = rp.j_inertia

    def m_throttle(self, x_throttle: float, p_drum: float) -> float:
        """Steam drawn from the drum through the throttle [kg/s]."""
        return self.tp.k_t * x_throttle * p_drum

    def m_chest_out(self, y: list[float]) -> float:
        """Turbine through-flow = exhaust to condenser [kg/s]."""
        return self.tp.k_t * y[self.i_pch]

    def p_mech(self, y: list[float]) -> float:
        """Mechanical power [W] = w_spec * chest through-flow."""
        return self.tp.w_spec * self.tp.k_t * y[self.i_pch]

    def chest_holdup(self, y: list[float]) -> float:
        """Transient steam mass stored in the chest [kg] (exact for this lag)."""
        return self.tp.k_t * self.tp.tau_chest * y[self.i_pch]

    def deriv(self, y: list[float], ydot: list[float], x_throttle: float,
              p_drum: float, p_elec: float) -> None:
        ydot[self.i_pch] = (x_throttle * p_drum - y[self.i_pch]) / self.tp.tau_chest
        omega = y[self.i_omega]
        p_m = self.p_mech(y)
        ydot[self.i_omega] = ((p_m - p_elec) / omega
                              - self.rp.d_m * (omega - self.rp.omega0)) / self._j
