"""Generic trip/alarm engine: per-condition timers, latching, first-out.

Evaluates table conditions against SENSED values each step. Actions fire once
on the activation edge; alarm state machine per condition is
clear -> active -> (acknowledged) -> clear. Latching conditions stay active
after the condition clears until an explicit reset. First-out records every
trip-class firing in order (scenario-injected trips are appended by the
simulator through record_external_trip).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hotwell.protection.tables import Condition, ProtectionTable

CLEAR = "clear"
ACTIVE = "active"
ACKED = "acknowledged"


@dataclass
class FiredAction:
    """One protective action requested by the engine this step."""

    t: float
    condition_id: str
    action: str          # alarm|mft|turbine_trip|trip_pump|shed_nonvital|safety_valve
    target: str | None = None
    value: bool = True   # safety_valve: True = open, False = reseat


@dataclass
class _CondState:
    met_since: float | None = None
    state: str = CLEAR
    latched: bool = False
    sv_open: bool = False  # hysteresis conditions only


@dataclass
class ProtectionEngine:
    table: ProtectionTable
    states: dict[str, _CondState] = field(default_factory=dict)
    first_out: list[tuple[float, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for c in self.table.conditions:
            self.states[c.id] = _CondState()

    # ------------------------------------------------------------------ step

    def evaluate(self, t: float, sensed: dict[str, float]) -> list[FiredAction]:
        """Evaluate all conditions at time t; returns actions firing this step."""
        fired: list[FiredAction] = []
        for c in self.table.conditions:
            st = self.states[c.id]
            met = c.met(sensed[c.signal])
            if c.reseat is not None:
                self._hysteresis(c, st, t, sensed[c.signal], met, fired)
                continue
            if met:
                if st.met_since is None:
                    st.met_since = t
                if st.state == CLEAR and (t - st.met_since) >= c.delay:
                    st.state = ACTIVE
                    st.latched = c.latching
                    self._fire(c, t, fired)
            else:
                st.met_since = None
                if st.state != CLEAR and not st.latched:
                    st.state = CLEAR
        return fired

    def _hysteresis(self, c: Condition, st: _CondState, t: float, value: float,
                    met: bool, fired: list[FiredAction]) -> None:
        if not st.sv_open and met:
            st.sv_open = True
            st.state = ACTIVE
            fired.append(FiredAction(t, c.id, "safety_valve", value=True))
        elif st.sv_open:
            reseated = value < c.reseat if c.op == "gt" else value > c.reseat
            if reseated:
                st.sv_open = False
                st.state = CLEAR
                fired.append(FiredAction(t, c.id, "safety_valve", value=False))

    def _fire(self, c: Condition, t: float, fired: list[FiredAction]) -> None:
        if c.is_trip:
            self.first_out.append((t, c.id))
        for a in c.actions:
            if a != "alarm":
                fired.append(FiredAction(t, c.id, a, target=c.target))

    # ------------------------------------------------------------ operator API

    def record_external_trip(self, t: float, label: str) -> None:
        """Scenario-injected or cascade trips join the first-out record."""
        self.first_out.append((t, label))

    def acknowledge(self, cid: str) -> bool:
        st = self.states.get(cid)
        if st is None or st.state != ACTIVE:
            return False
        st.state = ACKED
        return True

    def reset(self, t: float, sensed: dict[str, float]) -> list[str]:
        """Clear latches whose condition has cleared; returns cleared ids."""
        cleared = []
        for c in self.table.conditions:
            st = self.states[c.id]
            if st.latched and not c.met(sensed[c.signal]):
                st.latched = False
                st.state = CLEAR
                st.met_since = None
                cleared.append(c.id)
        return cleared

    def alarm_states(self) -> list[tuple[str, str]]:
        """All conditions not clear, as (id, state) in table order."""
        return [(c.id, self.states[c.id].state)
                for c in self.table.conditions
                if self.states[c.id].state != CLEAR]
