"""Action schema and validation — the panel's switch list and the agent's
tool surface in later phases. Boring and explicit by design.

An action submission is a flat dict of namespaced keys. Invalid commands are
rejected-and-recorded (never raise mid-run). Validity depends on current
discrete state and loop modes; see each entry's `validity` note.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionSpec:
    """One action key: type, bounds, and the validity condition (documentation
    string; enforcement lives in the simulator's apply-actions step)."""

    key: str
    kind: str        # 'bool' | 'float' | 'str'
    lo: float | None
    hi: float | None
    description: str
    validity: str


ACTION_SCHEMA: tuple[ActionSpec, ...] = tuple(
    [ActionSpec(f"{p}.start", "bool", None, None,
                f"start pump {p.upper()}",
                "pump stopped, start not inhibited, bus energized")
     for p in ("cp1", "cp2", "fp1", "fp2")]
    + [ActionSpec(f"{p}.stop", "bool", None, None,
                  f"stop pump {p.upper()}",
                  "pump starting or running")
       for p in ("cp1", "cp2", "fp1", "fp2")]
    + [
        ActionSpec("governor.load_ref_mw", "float", 0.0, 75.0,
                   "governor load reference [MW]", "always (clamped to bounds)"),
        ActionSpec("loads.nonvital.connect", "bool", None, None,
                   "connect/shed the non-vital load block", "bus energized"),
        ActionSpec("loop.drum_level.mode", "str", None, None,
                   "drum level loop auto|manual", "always"),
        ActionSpec("loop.drum_pressure.mode", "str", None, None,
                   "drum pressure loop auto|manual", "always"),
        ActionSpec("loop.da_level.mode", "str", None, None,
                   "DA level loop auto|manual", "always"),
        ActionSpec("fw_valve.manual_cmd", "float", 0.0, 1.0,
                   "feed reg valve manual command", "drum_level loop in manual"),
        ActionSpec("firing.manual_cmd", "float", 0.0, 1.0,
                   "firing manual command", "drum_pressure loop in manual, no MFT"),
        ActionSpec("da_lcv.manual_cmd", "float", 0.0, 1.0,
                   "DA level control valve manual command", "da_level loop in manual"),
        ActionSpec("alarm.ack", "str", None, None,
                   "acknowledge an active alarm by id", "alarm active"),
        ActionSpec("trips.reset", "bool", None, None,
                   "reset latched trips whose condition has cleared", "always"),
    ]
)

_SCHEMA_BY_KEY = {s.key: s for s in ACTION_SCHEMA}


def check_schema(key: str, value) -> str | None:
    """Static (state-free) validation; returns a rejection reason or None."""
    spec = _SCHEMA_BY_KEY.get(key)
    if spec is None:
        return f"unknown action key: {key}"
    if spec.kind == "bool" and not isinstance(value, bool):
        return f"{key}: expected bool, got {type(value).__name__}"
    if spec.kind == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"{key}: expected number, got {type(value).__name__}"
        if spec.lo is not None and not (spec.lo <= value <= spec.hi):
            return f"{key}: {value} outside [{spec.lo}, {spec.hi}]"
    if spec.kind == "str" and not isinstance(value, str):
        return f"{key}: expected str, got {type(value).__name__}"
    if key.startswith("loop.") and value not in ("auto", "manual"):
        return f"{key}: mode must be 'auto' or 'manual'"
    return None
