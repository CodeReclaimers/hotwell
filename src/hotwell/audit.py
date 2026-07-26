"""Mass and energy closure diagnostics.

Mass: total water inventory (drum + hotwell + DA + chest holdup + fixed piping
constant) is conserved in the closed cycle except for integrated safety-valve
relief. Energy (steady state): Q_fire_effective - (P_e + Q_cond + declared
losses); declared losses = rotor mechanical damping. Both reported as
fractions per plan section 10.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AuditReport:
    """Snapshot of closure diagnostics."""

    t: float                    # [s]
    mass_total: float           # [kg] current tracked inventory
    mass_relief_integrated: float  # [kg] cumulative safety-valve loss
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

    def reset(self, t: float, mass_total: float) -> None:
        self.m0 = mass_total
        self.t0 = t
        self.relief_kg = 0.0

    def accumulate(self, m_relief: float, dt: float) -> None:
        """Add one step's safety-valve relief mass [kg]."""
        self.relief_kg += m_relief * dt

    def report(self, t: float, mass_total: float, q_fire: float, p_elec: float,
               q_cond: float, p_damping: float) -> AuditReport:
        drift = (mass_total + self.relief_kg - self.m0) / self.m0 if self.m0 else 0.0
        hours = (t - self.t0) / 3600.0
        resid = q_fire - (p_elec + q_cond + p_damping)
        return AuditReport(
            t=t,
            mass_total=mass_total,
            mass_relief_integrated=self.relief_kg,
            mass_drift_frac=drift,
            mass_drift_frac_per_hour=drift / hours if hours > 0 else 0.0,
            energy_residual=resid,
            energy_residual_frac=resid / q_fire if q_fire > 0 else 0.0,
        )
