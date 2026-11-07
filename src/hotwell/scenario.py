"""Scenario loading and event application (plan section 9).

Event types: trip_pump, inhibit_start, sensor_fault, set_air_ingress, action,
set_load (load-block demand step — needed by the load_step canonical scenario;
minimal extension recorded in HANDOFF).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from hotwell import data
from hotwell.sensors import OBSERVATION_SPEC, SENSOR_FAULT_KINDS, SensorFault

_INSTRUMENTS = {s.name for s in OBSERVATION_SPEC}

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


def _check_sensor_fault(scenario: str, p: dict) -> None:
    """Fail at load time, not mid-run, on a malformed sensor_fault (0.4.0)."""
    where = f"{scenario}: sensor_fault"
    if p.get("target") not in _INSTRUMENTS:
        raise ValueError(f"{where}: unknown target instrument {p.get('target')!r}")
    kind = p.get("kind")
    if kind not in SENSOR_FAULT_KINDS:
        raise ValueError(f"{where}: unknown kind {kind!r}")
    missing = [k for k in SENSOR_FAULT_KINDS[kind] if k not in p]
    if missing:
        raise ValueError(f"{where} kind {kind!r}: missing {missing}")
    # constructing the fault runs its own range checks (tau_s > 0, factor >= 0)
    SensorFault(kind=kind, **{k: float(p[k]) for k in
                              ("bias", "rate", "max_bias", "tau_s", "factor") if k in p})


def load_scenario(path: data.Resource) -> Scenario:
    """Parse and validate a scenario YAML (filesystem path or packaged resource)."""
    raw = yaml.safe_load(data.read_text(path))
    events = []
    for row in raw.get("events", ()):
        etype = row["type"]
        if etype not in EVENT_TYPES:
            raise ValueError(f"{raw['name']}: unknown event type {etype!r}")
        params = {k: v for k, v in row.items() if k not in ("t", "type")}
        if etype == "sensor_fault":
            _check_sensor_fault(raw["name"], params)
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
