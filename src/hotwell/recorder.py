"""Record a driven run as a replayable scenario (0.4.0, plan M6).

`ActionRecorder` wraps `Simulator.step` and logs EVERYTHING that enters the
simulator from outside, in application order: the scenario events that fired
on each tick (first, as `step()` applies them first), then the submitted
action dict. The output scenario is built entirely from that log, never from
the original scenario plus a diff, so a tick carrying both an event and an
action replays in live order. `load_scenario` sorts stably, and every record
of one tick shares one stamp.

Stamps are **half a tick early**: (tick - 1/2)*dt. `step()` fires events
on `ev.t <= sim.t + 1e-9`, where `sim.t` is an accumulated sum of dt whose
error grows with run length (the panel measured -1.089e-9 s at 36 000 ticks;
a 24 h run is 1.728 M ticks). An exact stamp would fire some events one step
late; half a tick early leaves 0.025 s of margin either way. Reference:
hotwell-panel `sessionlog.py`. This is new core code; the panel adopting it
is a separate panel task.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from hotwell.scenario import Scenario, ScenarioEvent
from hotwell.simulator import DT, Simulator


@dataclass(frozen=True)
class Record:
    tick: int
    kind: str       # a scenario event type, or "action"
    params: dict

    @property
    def fire_t(self) -> float:
        return (self.tick - 0.5) * DT


class ActionRecorder:
    """Drive `sim` through `step()` and keep the replay log."""

    def __init__(self, sim: Simulator) -> None:
        self.sim = sim
        self.records: list[Record] = []

    def step(self, actions: dict | None = None):
        sim = self.sim
        tick = int(round(sim.t / DT))
        i0 = sim._event_idx
        obs = sim.step(actions)
        if sim.scenario is not None:
            for ev in sim.scenario.events[i0:sim._event_idx]:
                self.records.append(Record(tick, ev.type, dict(ev.params)))
        if actions:
            self.records.append(Record(tick, "action", {"command": dict(actions)}))
        return obs

    def to_scenario(self, name: str | None = None) -> Scenario:
        sc = self.sim.scenario
        assert sc is not None, "recording needs a scenario for seed/init/max_t"
        events = tuple(ScenarioEvent(r.fire_t, r.kind, r.params) for r in self.records)
        return Scenario(name=name or f"{sc.name}_recorded", seed=sc.seed, load_mw=sc.load_mw,
                        mode=sc.mode, events=events, max_t=sc.max_t)

    def to_yaml(self, path: str | Path, name: str | None = None) -> Path:
        sc = self.to_scenario(name)
        doc = {"name": sc.name, "seed": sc.seed,
               "init": {"load_mw": sc.load_mw, "mode": sc.mode},
               "events": [{"t": e.t, "type": e.type, **e.params} for e in sc.events],
               "end": {"max_t": sc.max_t}}
        p = Path(path)
        p.write_text("# Recorded by hotwell.recorder.ActionRecorder; replays bit-identically\n"
                     "# with the same plant config.\n"
                     + yaml.safe_dump(doc, sort_keys=False))
        return p


def drive(sim: Simulator, until: float, runner=None, schedule=(), recorder=None) -> None:
    """Run to `until` with an optional background operator.

    schedule: iterable of (t, proc_id, params): procedure start requests.
    The runner's actions go through `recorder.step` if given, else `sim.step`.
    """
    pending = sorted(schedule, key=lambda s: s[0])
    stepper = recorder.step if recorder is not None else sim.step
    while sim.t < until - 0.5 * sim.dt:
        while pending and pending[0][0] <= sim.t + 1e-9:
            t0, pid, params = pending.pop(0)
            runner.start(pid, params, sim.t)
        actions = runner.tick(sim.last_obs, sim.loop_state(), sim.t) if runner else {}
        stepper(actions or None)
        if sim.last_obs.plant_dead:
            break
