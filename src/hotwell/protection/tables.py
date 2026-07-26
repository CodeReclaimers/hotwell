"""Load the protection/alarm YAML table into dataclasses (plan section 7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_TABLE = Path(__file__).resolve().parents[3] / "data" / "protection.yaml"

VALID_ACTIONS = {"alarm", "mft", "turbine_trip", "trip_pump", "shed_nonvital",
                 "safety_valve"}
TRIP_CLASS = {"mft", "turbine_trip", "trip_pump"}


@dataclass(frozen=True)
class Condition:
    """One alarm/trip condition from the table. Units are the signal's SI units."""

    id: str
    signal: str
    op: str                  # 'lt' | 'gt'
    setpoint: float
    delay: float             # [s]
    latching: bool
    actions: tuple[str, ...]
    target: str | None = None   # pump name for trip_pump
    reseat: float | None = None  # hysteresis reseat setpoint (safety valve)

    @property
    def is_trip(self) -> bool:
        return bool(TRIP_CLASS.intersection(self.actions))

    def met(self, value: float) -> bool:
        return value < self.setpoint if self.op == "lt" else value > self.setpoint


@dataclass(frozen=True)
class ProtectionTable:
    conditions: tuple[Condition, ...] = field(default_factory=tuple)

    def by_id(self, cid: str) -> Condition:
        for c in self.conditions:
            if c.id == cid:
                return c
        raise KeyError(cid)


def load_protection_table(path: str | Path | None = None) -> ProtectionTable:
    """Parse and validate the YAML table."""
    with open(path or DEFAULT_TABLE) as f:
        raw = yaml.safe_load(f)
    conds = []
    seen: set[str] = set()
    for row in raw["conditions"]:
        cid = row["id"]
        if cid in seen:
            raise ValueError(f"duplicate condition id: {cid}")
        seen.add(cid)
        actions = tuple(row["actions"])
        bad = set(actions) - VALID_ACTIONS
        if bad:
            raise ValueError(f"{cid}: unknown actions {bad}")
        if "trip_pump" in actions and not row.get("target"):
            raise ValueError(f"{cid}: trip_pump requires a target")
        if "safety_valve" in actions and row.get("reseat") is None:
            raise ValueError(f"{cid}: safety_valve requires a reseat setpoint")
        if row["op"] not in ("lt", "gt"):
            raise ValueError(f"{cid}: op must be lt|gt")
        conds.append(Condition(
            id=cid, signal=row["signal"], op=row["op"],
            setpoint=float(row["setpoint"]), delay=float(row["delay"]),
            latching=bool(row["latching"]), actions=actions,
            target=row.get("target"), reseat=row.get("reseat")))
    return ProtectionTable(conditions=tuple(conds))
