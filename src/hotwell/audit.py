"""Mass and energy closure diagnostics.

Mass: total water inventory (drum + hotwell + DA + chest holdup + fixed piping
constant) is conserved in the closed cycle except for integrated safety-valve
relief, and (0.4.0 M5b) the boundary flows: tube-leak loss out, CST makeup in.
Energy (steady state): Q_fire_effective + m_mu*h_mu - m_leak*h_leak
- (P_e + Q_cond + declared losses); declared losses = rotor mechanical
damping. Both reported as fractions per plan section 10. Leak and makeup are
integrated with the trapezoid rule (they vary continuously); relief keeps its
original end-of-step rule.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AuditReport:
    """Snapshot of closure diagnostics."""

    t: float                    # [s]
    mass_total: float           # [kg] current tracked inventory
    mass_relief_integrated: float  # [kg] cumulative safety-valve loss
    mass_leak_integrated: float    # [kg] cumulative tube-leak loss (0.4.0)
    mass_makeup_integrated: float  # [kg] cumulative CST makeup (0.4.0)
    mass_drift_frac: float      # [-] (M + relief - M0)/M0
    mass_drift_frac_per_hour: float  # [1/h]
    energy_residual: float      # [W] instantaneous Q_fire - (P_e + Q_cond + losses)
    energy_residual_frac: float  # [-] residual / Q_fire


class AuditAccumulator:
    """Integrates relief loss and reports closure. Owned by the simulator."""

    def __init__(self) -> None:
        self.m0 = 0.0
        self.t0 = 0.0
        self.relief_kg = 0.0
        self.leak_kg = 0.0
        self.makeup_kg = 0.0
        self._last_leak = 0.0
        self._last_makeup = 0.0

    def reset(self, t: float, mass_total: float) -> None:
        self.m0 = mass_total
        self.t0 = t
        self.relief_kg = 0.0
        self.leak_kg = 0.0
        self.makeup_kg = 0.0
        self._last_leak = 0.0
        self._last_makeup = 0.0

    def accumulate(self, m_relief: float, dt: float, m_leak: float = 0.0,
                   m_makeup: float = 0.0) -> None:
        """Add one step's boundary masses [kg]: relief (end-of-step rule, as
        before) and leak/makeup (trapezoid on this and the previous step)."""
        self.relief_kg += m_relief * dt
        if m_leak or self._last_leak:
            self.leak_kg += 0.5 * (m_leak + self._last_leak) * dt
        if m_makeup or self._last_makeup:
            self.makeup_kg += 0.5 * (m_makeup + self._last_makeup) * dt
        self._last_leak, self._last_makeup = m_leak, m_makeup

    def report(self, t: float, mass_total: float, q_fire: float, p_elec: float,
               q_cond: float, p_damping: float, e_in: float = 0.0,
               e_out: float = 0.0) -> AuditReport:
        """e_in / e_out [W]: boundary enthalpy flows (makeup in, leak out)."""
        net = mass_total + self.relief_kg + self.leak_kg - self.makeup_kg
        drift = (net - self.m0) / self.m0 if self.m0 else 0.0
        hours = (t - self.t0) / 3600.0
        resid = q_fire + e_in - e_out - (p_elec + q_cond + p_damping)
        return AuditReport(
            t=t,
            mass_total=mass_total,
            mass_relief_integrated=self.relief_kg,
            mass_leak_integrated=self.leak_kg,
            mass_makeup_integrated=self.makeup_kg,
            mass_drift_frac=drift,
            mass_drift_frac_per_hour=drift / hours if hours > 0 else 0.0,
            energy_residual=resid,
            energy_residual_frac=resid / q_fire if q_fire > 0 else 0.0,
        )
