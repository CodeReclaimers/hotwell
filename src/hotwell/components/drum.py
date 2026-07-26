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
