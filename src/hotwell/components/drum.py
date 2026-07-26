"""Drum boiler: stable interface (phase-agnostic) + phase-1 two-state model.

Interface contract (section 5.2 of the plan): inputs are effective firing heat
Q_fire [W], feed flow m_fw [kg/s], feed enthalpy h_fw [J/kg], and steam flow
drawn m_s [kg/s]; outputs are drum pressure p [Pa], drum level l [m, relative
to normal water level NWL = 0], and steam enthalpy h_g(p) [J/kg]. The M4
AstromBellDrum swap must change nothing outside this file.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from hotwell.state import StateRegistry


@dataclass(frozen=True)
class DrumOutputs:
    """Algebraic outputs of the drum closure at one state evaluation."""

    p: float        # drum pressure [Pa]
    level: float    # drum level relative to NWL [m]
    h_steam: float  # saturated steam enthalpy h_g(p) [J/kg]


class DrumBoiler(ABC):
    """Stable drum-boiler interface; concrete models own their ODE states."""

    @abstractmethod
    def register_states(self, reg: StateRegistry) -> None:
        """Declare this model's continuous states (indices kept internally)."""

    @abstractmethod
    def outputs(self, y: np.ndarray) -> DrumOutputs:
        """Solve the model's algebraic closure at state y; warm-started, cheap."""

    @abstractmethod
    def derivatives(self, y: np.ndarray, ydot: np.ndarray, out: DrumOutputs,
                    q_fire: float, m_fw: float, h_fw: float, m_s: float) -> None:
        """Write d/dt of this model's states into ydot.

        q_fire [W] effective heat to fluid; m_fw [kg/s] feed flow; h_fw [J/kg]
        feed enthalpy; m_s [kg/s] total steam drawn (turbine + auxiliary + relief).
        """


@dataclass(frozen=True)
class TwoStateDrumParams:
    v_total: float      # drum+riser fluid volume [m3]
    v_liq_nwl: float    # liquid volume at normal water level [m3]
    a_waterplane: float  # effective waterplane area [m2] (vertical-cylinder equiv.)
    p_min: float = 3.2e6   # closure clamp, low [Pa] (fit range guard)
    p_max: float = 11.8e6  # closure clamp, high [Pa]


class TwoStateDrum(DrumBoiler):
    """Phase-1 drum: saturated equilibrium mixture (M, U) in fixed volume.

    dM/dt = m_fw - m_s;  dU/dt = q_fire + m_fw*h_fw - m_s*h_g(p).
    Closure: find (p, x) with M*v_mix(p,x) = V and M*u_mix(p,x) = U, damped
    Newton warm-started from the previous solve. Level is monotone in liquid
    volume (no shrink/swell — accepted phase-1 limitation, see T9).
    """

    def __init__(self, params: TwoStateDrumParams) -> None:
        self.p = params
        self.i_m = -1
        self.i_u = -1
        self._p_warm = 8.0e6
        self._x_warm = 0.05

    def register_states(self, reg: StateRegistry) -> None:
        # initials are placeholders; initialize_steady_state overwrites them
        self.i_m = reg.register("drum.M", 10.7e3, "kg", 4.0e3)
        self.i_u = reg.register("drum.U", 1.47e10, "J", 4.0e9)

    def solve_closure(self, m: float, u: float) -> tuple[float, float]:
        """Return (p [Pa], quality x [-]) with M*v_mix = V, M*u_mix = U."""
        from hotwell import steam_properties as sp

        v_spec = self.p.v_total / m
        u_spec = u / m
        p = self._p_warm
        x = self._x_warm
        for _ in range(30):
            vf = sp.v_f(p)
            vg = sp.v_g(p)
            uf = sp.u_f(p)
            ug = sp.u_g(p)
            vfg = vg - vf
            ufg = ug - uf
            f1 = vf + x * vfg - v_spec
            f2 = uf + x * ufg - u_spec
            # Jacobian
            j11 = sp.dv_f_dp(p) + x * (sp.dv_g_dp(p) - sp.dv_f_dp(p))
            j12 = vfg
            j21 = sp.du_f_dp(p) + x * (sp.du_g_dp(p) - sp.du_f_dp(p))
            j22 = ufg
            det = j11 * j22 - j12 * j21
            dp = (-f1 * j22 + f2 * j12) / det
            dx = (-f2 * j11 + f1 * j21) / det
            # damping: limit pressure step to 1 MPa, x step to 0.2
            if dp > 1e6:
                dp = 1e6
            elif dp < -1e6:
                dp = -1e6
            if dx > 0.2:
                dx = 0.2
            elif dx < -0.2:
                dx = -0.2
            p += dp
            x += dx
            if p < self.p.p_min:
                p = self.p.p_min
            elif p > self.p.p_max:
                p = self.p.p_max
            if x < 1e-6:
                x = 1e-6
            elif x > 0.9:
                x = 0.9
            if abs(dp) < 1e-3 and abs(dx) < 1e-9:
                break
        self._p_warm = p
        self._x_warm = x
        return p, x

    def outputs(self, y: np.ndarray | list[float]) -> DrumOutputs:
        from hotwell import steam_properties as sp

        m = y[self.i_m]
        u = y[self.i_u]
        p, x = self.solve_closure(m, u)
        v_liq = m * (1.0 - x) * sp.v_f(p)
        level = (v_liq - self.p.v_liq_nwl) / self.p.a_waterplane
        return DrumOutputs(p=p, level=level, h_steam=sp.h_g(p))

    def derivatives(self, y: list[float], ydot: list[float], out: DrumOutputs,
                    q_fire: float, m_fw: float, h_fw: float, m_s: float) -> None:
        ydot[self.i_m] = m_fw - m_s
        ydot[self.i_u] = q_fire + m_fw * h_fw - m_s * out.h_steam
