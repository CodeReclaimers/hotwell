"""Condenser (algebraic pressure) + hotwell inventory.

p_cond = p0 + p_load_slope * (m_exhaust / m_exh_rated) + air_ingress [Pa]
— mild monotone load dependence; air_ingress is a scenario-settable additive
term (default 0), the hook for the later condenser-air-leak casualty.
Condensate leaves at Tsat(p_cond). Condenser heat duty (for the energy
audit): Q_cond = m_exhaust * (h_exhaust - h_f(p_cond)).
"""
from __future__ import annotations

from dataclasses import dataclass

from hotwell import steam_properties as sp
from hotwell.state import StateRegistry


@dataclass(frozen=True)
class CondenserParams:
    p0: float             # condenser pressure at zero exhaust [Pa]
    p_load_slope: float   # added pressure at rated exhaust [Pa]
    m_exh_rated: float    # rated exhaust flow [kg/s]
    a_hotwell: float      # hotwell waterplane area [m2]
    hw_level_nominal: float  # nominal hotwell depth above its bottom [m]
    z_hw: float           # hotwell bottom elevation above CP suction [m]


class Condenser:
    """Algebraic condenser + hotwell mass state."""

    def __init__(self, params: CondenserParams, reg: StateRegistry) -> None:
        self.p = params
        self.i_m = reg.register("hotwell.M", 8.0e3, "kg", 6.0e3)

    def p_cond(self, m_exhaust: float, air_ingress: float,
               fouling_factor: float = 1.0) -> float:
        """Condenser pressure [Pa]. `fouling_factor` (0.4.0 M5) scales the
        load-dependent term (tube fouling worsens heat transfer in proportion
        to duty); air ingress is additive. Load dependence separates the two."""
        return self.p.p0 + (self.p.p_load_slope * fouling_factor) \
            * (m_exhaust / self.p.m_exh_rated) + air_ingress

    def level_abs(self, y: list[float], rho: float) -> float:
        """Hotwell level above hotwell bottom [m]."""
        return y[self.i_m] / (rho * self.p.a_hotwell)

    def level_rel(self, y: list[float], rho: float) -> float:
        """Hotwell level relative to nominal [m]."""
        return self.level_abs(y, rho) - self.p.hw_level_nominal

    def m_nominal(self, rho: float) -> float:
        """Hotwell inventory at nominal level [kg]."""
        return rho * self.p.a_hotwell * self.p.hw_level_nominal

    def deriv(self, y: list[float], ydot: list[float],
              m_exhaust: float, m_out: float, m_makeup: float = 0.0) -> None:
        ydot[self.i_m] = m_exhaust + m_makeup - m_out

    @staticmethod
    def q_cond(m_exhaust: float, h_exhaust: float, p_cond: float,
               m_makeup: float = 0.0, h_makeup: float = 0.0) -> float:
        """Condenser heat duty [W] for the energy audit. 0.4.0 M5b: makeup is
        sprayed into the condenser and heated to Tsat(p_cond) by condensing
        steam, so the duty to cooling water falls by m_mu (h_c - h_mu)."""
        t_c = sp.tsat_lowp(p_cond)
        h_c = sp.hf_t(t_c)
        q = m_exhaust * (h_exhaust - h_c)
        if m_makeup != 0.0:
            q -= m_makeup * (h_c - h_makeup)
        return q
