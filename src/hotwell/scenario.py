"""Scenario loading and event application (plan section 9).

Event types: trip_pump, inhibit_start, sensor_fault, set_air_ingress, action,
set_load (load-block demand step — needed by the load_step canonical scenario;
minimal extension recorded in HANDOFF).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

EVENT_TYPES = {"trip_pump", "inhibit_start", "sensor_fault", "set_air_ingress",
               "action", "set_load"}


@dataclass(frozen=True)
class ScenarioEvent:
    t: float           # [s]
    type: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    name: str
    seed: int
    load_mw: float
    mode: str
    events: tuple[ScenarioEvent, ...]
    max_t: float


def load_scenario(path: str | Path) -> Scenario:
    """Parse and validate a scenario YAML."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    events = []
    for row in raw.get("events", ()):
        etype = row["type"]
        if etype not in EVENT_TYPES:
            raise ValueError(f"{raw['name']}: unknown event type {etype!r}")
        params = {k: v for k, v in row.items() if k not in ("t", "type")}
        events.append(ScenarioEvent(t=float(row["t"]), type=etype, params=params))
    events.sort(key=lambda e: e.t)
    return Scenario(
        name=raw["name"],
        seed=int(raw.get("seed", 0)),
        load_mw=float(raw["init"]["load_mw"]),
        mode=raw["init"].get("mode", "islanded"),
        events=tuple(events),
        max_t=float(raw["end"]["max_t"]),
    )
