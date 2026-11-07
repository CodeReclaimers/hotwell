"""Turbine: throttle flow law, steam chest lag, mechanical power, rotor swing.

Throttle (choked approximation): m_throttle = k_t * x * p_drum [kg/s].
Steam chest: tau_ch * dp_chest/dt = x * p_drum - p_chest — a first-order lag
between valve-commanded flow and mechanical power. Turbine through-flow
(= exhaust to condenser) is k_t * p_chest, so transient chest storage is
exactly k_t * tau_ch * p_chest [kg] (counted in the mass audit).

Swing (islanded): J * domega/dt = (P_m - P_e)/omega - D_m*(omega - omega0).

Specific work (0.4.0, plan M2): w(p_drum, p_cond) = eta_t * dh_s, where dh_s
is the isentropic enthalpy drop from saturated vapour at drum pressure into
the wet region at condenser pressure:
    x_2s = (s_g(p_drum) - s_f(T_c)) / s_fg(T_c),  s_fg = h_fg / T_c (exact)
    h_2s = h_f(T_c) + x_2s * h_fg(T_c),           T_c = Tsat(p_cond)
eta_t is derived once (`set_design`) so that w equals `w_design` exactly at
the design state. That keeps k_t, the droop calibration and the 60 MW anchor
exact. Documented simplification: the expansion starts from the DRUM state,
so the governor valve's throttling loss is not modelled (that would need
superheated-steam properties).
"""
from __future__ import annotations

from dataclasses import dataclass

from hotwell import steam_properties as sp
from hotwell.state import StateRegistry


@dataclass(frozen=True)
class TurbineParams:
    k_t: float       # throttle flow coefficient [kg/(s*Pa)]
    w_design: float  # specific work at the design state [J/kg] (calibrates eta_t)
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


def isentropic_drop(p_in: float, p_cond: float) -> float:
    """Isentropic enthalpy drop [J/kg] from saturated vapour at p_in [Pa]
    (3–12 MPa) to p_cond [Pa] (4.2–476 kPa). See module docstring."""
    t_c = sp.tsat_lowp(p_cond)
    h_f = sp.hf_t(t_c)
    h_fg = sp.hg_t(t_c) - h_f
    x_2s = (sp.s_g(p_in) - sp.sf_t(t_c)) / (h_fg / t_c)
    return sp.h_g(p_in) - (h_f + x_2s * h_fg)


class Turbine:
    """Steam chest + rotor states; algebraic flow/power helpers."""

    def __init__(self, tp: TurbineParams, rp: RotorParams, reg: StateRegistry) -> None:
        self.tp = tp
        self.rp = rp
        self.i_pch = reg.register("chest.p", 6.8e6, "Pa", 8.0e6)
        self.i_omega = reg.register("rotor.omega", rp.omega0, "rad/s", 40.0)
        self._j = rp.j_inertia
        self.eta_t: float | None = None  # set by set_design()

    def set_design(self, p_drum: float, p_cond: float) -> None:
        """Derive eta_t so that specific_work(p_drum, p_cond) == w_design.
        Called once by the Plant with the design state."""
        self.eta_t = self.tp.w_design / isentropic_drop(p_drum, p_cond)

    def specific_work(self, p_drum: float, p_cond: float) -> float:
        """Specific work [J/kg] = eta_t * isentropic drop (0.4.0)."""
        assert self.eta_t is not None, "Turbine.set_design() not called"
        return self.eta_t * isentropic_drop(p_drum, p_cond)

    def m_throttle(self, x_throttle: float, p_drum: float) -> float:
        """Steam drawn from the drum through the throttle [kg/s]."""
        return self.tp.k_t * x_throttle * p_drum

    def m_chest_out(self, y: list[float]) -> float:
        """Turbine through-flow = exhaust to condenser [kg/s]."""
        return self.tp.k_t * y[self.i_pch]

    def p_mech(self, y: list[float], w: float) -> float:
        """Mechanical power [W] = specific work w [J/kg] * chest through-flow."""
        return w * self.tp.k_t * y[self.i_pch]

    def chest_holdup(self, y: list[float]) -> float:
        """Transient steam mass stored in the chest [kg] (exact for this lag)."""
        return self.tp.k_t * self.tp.tau_chest * y[self.i_pch]

    def deriv(self, y: list[float], ydot: list[float], x_throttle: float,
              p_drum: float, p_elec: float, w: float) -> None:
        ydot[self.i_pch] = (x_throttle * p_drum - y[self.i_pch]) / self.tp.tau_chest
        omega = y[self.i_omega]
        p_m = self.p_mech(y, w)
        ydot[self.i_omega] = ((p_m - p_elec) / omega
                              - self.rp.d_m * (omega - self.rp.omega0)) / self._j
