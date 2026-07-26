"""Flat continuous-state vector with named slots declared by components.

Each component registers its own state slots (name, initial value, units,
nominal span) against a StateRegistry at plant-build time and keeps the
returned integer indices for hot-path access. The simulator integrates the
flat numpy array; nothing outside the registry knows global ordering.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class StateSlot:
    """One continuous state: name like 'drum.M', initial value, units string,
    and a nominal span used for drift diagnostics (T2)."""

    name: str
    initial: float
    units: str
    span: float


class StateRegistry:
    """Ordered registry of continuous state slots.

    Components call register() during plant construction; the returned index
    is stable for the life of the plant and is how components address their
    states inside the derivative function.
    """

    def __init__(self) -> None:
        self._slots: list[StateSlot] = []
        self._index: dict[str, int] = {}

    def register(self, name: str, initial: float, units: str, span: float) -> int:
        """Declare a state slot; returns its index in the flat state vector."""
        if name in self._index:
            raise ValueError(f"duplicate state name: {name}")
        if span <= 0.0:
            raise ValueError(f"state {name}: span must be positive, got {span}")
        idx = len(self._slots)
        self._slots.append(StateSlot(name, float(initial), units, float(span)))
        self._index[name] = idx
        return idx

    @property
    def n(self) -> int:
        return len(self._slots)

    @property
    def slots(self) -> tuple[StateSlot, ...]:
        return tuple(self._slots)

    def index(self, name: str) -> int:
        return self._index[name]

    def names(self) -> list[str]:
        return [s.name for s in self._slots]

    def initial_vector(self) -> np.ndarray:
        """Fresh state vector [mixed units] populated with declared initials."""
        return np.array([s.initial for s in self._slots], dtype=np.float64)

    def spans(self) -> np.ndarray:
        """Nominal span per state [same units as the state], for drift checks."""
        return np.array([s.span for s in self._slots], dtype=np.float64)

    def as_dict(self, y: np.ndarray) -> dict[str, float]:
        """Name -> value view of a state vector (diagnostics only, not hot path)."""
        return {s.name: float(y[i]) for i, s in enumerate(self._slots)}
