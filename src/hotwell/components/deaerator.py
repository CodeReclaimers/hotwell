"""Deaerator: fixed-pressure saturated feedwater reservoir with mass state.

The DA is held at fixed pressure p_da (phase-1 simplification); its liquid is
saturated at Tsat(p_da), which sets feedwater enthalpy and density. Pegging
(auxiliary) steam from the drum heats incoming condensate up to saturation —
computed algebraically from the DA inlet energy balance; this is what closes
the plant energy audit (see HANDOFF).
"""
from __future__ import annotations

from dataclasses import dataclass

from hotwell import steam_properties as sp
from hotwell.state import StateRegistry


@dataclass(frozen=True)
class DeaeratorParams:
    p_da: float           # operating pressure [Pa] (fixed)
    area: float           # tank waterplane area [m2]
    level_nominal: float  # normal level above tank bottom [m]
    z_da: float           # tank bottom elevation above feed pump suction [m]


class Deaerator:
    """Feedwater reservoir; owns da.M."""

    def __init__(self, params: DeaeratorParams, reg: StateRegistry) -> None:
        self.p = params
        self.t_sat = sp.tsat_lowp(params.p_da)   # [K]
        self.h_fw = sp.hf_t(self.t_sat)          # feedwater enthalpy [J/kg]
        self.rho = sp.rho_f_t(self.t_sat)        # feedwater density [kg/m3]
        self.i_m = reg.register("da.M", self.m_nominal(), "kg", 6.0e3)

    def m_nominal(self) -> float:
        """Inventory at normal level [kg]."""
        return self.rho * self.p.area * self.p.level_nominal

    def level_abs(self, y: list[float]) -> float:
        """Level above tank bottom [m] (floored at empty)."""
        lvl = y[self.i_m] / (self.rho * self.p.area)
        return lvl if lvl > 0.0 else 0.0

    def level_rel(self, y: list[float]) -> float:
        """Level relative to normal [m]."""
        return self.level_abs(y) - self.p.level_nominal

    def m_pegging(self, m_cond_in: float, h_cond_in: float, p_drum: float,
                  h_g_drum: float) -> float:
        """Pegging steam flow [kg/s] that heats incoming condensate to saturation.

        m_peg = m_cond * (h_fw - h_cond) / (h_g(p_drum) - h_fw), drawn from the
        drum steam space; zero when there is no condensate inflow or no drum
        pressure to supply it.
        """
        if m_cond_in <= 0.0 or p_drum < 2.0 * self.p.p_da:
            return 0.0
        dh = h_g_drum - self.h_fw
        if dh <= 0.0:
            return 0.0
        return m_cond_in * (self.h_fw - h_cond_in) / dh

    def deriv(self, y: list[float], ydot: list[float], m_cond_in: float,
              m_peg: float, m_fw_out: float) -> None:
        ydot[self.i_m] = m_cond_in + m_peg - m_fw_out
