"""Operating procedures as data, and the closed-loop background operator
(0.4.0, plan M6).

Procedures live in `hotwell/data/procedures/*.yaml`. The SAME files render
into the manual's normal operating procedures (M7) and drive the runner, so
what the manual prints and what the scripted operator does can't diverge.

Schema (one procedure per file):

    id, title, purpose            strings
    params: {name: default}       templated into every string as "{name}"
    applies_when: [cond, ...]     checked at start; unmet -> "not_applicable"
    steps: [step, ...]            run in order
    contingencies: {id: step}     reached only via goto; must end the procedure

    cond (data, never eval):
      {signal: <instrument>, op: lt|gt|le|ge, value: <float>}   on Observation.values
      {indication: <name>, eq: <bool>}                          on Observation.indications

    step kinds (exactly one of do / hold / trim / ack_active, plus id and text):
      do: {action dict}         submit once, then if wait_for: wait until all conds
                                hold, `within` seconds, else on_timeout {goto: id}
      hold: <s>                 wait; then if `check` conds fail -> on_fail {goto: id}
      trim: {signal, target, deadband, key, base, gain, max_step, settle_s,
             max_moves}         move an absolute setpoint `key` from loop-state
                                `base` by -gain*(signal - target), clamped to
                                +-max_step, every settle_s, until within deadband
                                (or max_moves -> outcome "trim_incomplete")
      ack_active: true          acknowledge every active alarm, one per tick
    contingency extra key: outcome: <word>   (default "aborted")

Runner semantics: one procedure at a time (FIFO queue); a reaction delay
before every step (fixed `reaction_s`, or lognormal from the `operator`
stream); the runner reads only the Observation and `Simulator.loop_state()`,
never truth. It does no casualty response; that's item design (bench repo).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import yaml

from hotwell import data
from hotwell.actions import check_schema
from hotwell.sensors import OBSERVATION_SPEC

_OPS = {"lt": lambda a, b: a < b, "gt": lambda a, b: a > b,
        "le": lambda a, b: a <= b, "ge": lambda a, b: a >= b}
_INSTRUMENTS = {s.name for s in OBSERVATION_SPEC}
_KINDS = ("do", "hold", "trim", "ack_active")
_TEMPLATE = re.compile(r"\{(\w+)\}")


def _fill(obj, params: dict):
    """Recursively substitute {name} in strings (keys and values)."""
    if isinstance(obj, str):
        return _TEMPLATE.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params
                             else m.group(0), obj)
    if isinstance(obj, dict):
        return {_fill(k, params): _fill(v, params) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fill(v, params) for v in obj]
    return obj


def _check_cond(where: str, c: dict) -> None:
    if "signal" in c:
        if c["signal"] not in _INSTRUMENTS:
            raise ValueError(f"{where}: unknown instrument {c['signal']!r}")
        if c.get("op") not in _OPS or not isinstance(c.get("value"), (int, float)):
            raise ValueError(f"{where}: signal condition needs op in {sorted(_OPS)} and value")
    elif "indication" in c:
        if not isinstance(c.get("eq"), bool):
            raise ValueError(f"{where}: indication condition needs eq: true|false")
    else:
        raise ValueError(f"{where}: condition needs 'signal' or 'indication': {c}")


@dataclass(frozen=True)
class Procedure:
    id: str
    title: str
    purpose: str
    params: dict
    raw: dict      # the unfilled YAML (for rendering)

    def filled(self, params: dict | None = None) -> dict:
        p = {**self.params, **(params or {})}
        return _fill(self.raw, p)


def validate(proc: Procedure, params: dict | None = None) -> None:
    """Static validation of a procedure with given params. Every action key is
    run through actions.check_schema; every condition and goto is checked."""
    d = proc.filled(params)
    where = proc.id
    for c in d.get("applies_when", []):
        _check_cond(f"{where} applies_when", c)
    cont = d.get("contingencies", {}) or {}

    def check_step(s: dict, ctx: str) -> None:
        kinds = [k for k in _KINDS if k in s]
        if len(kinds) != 1 and not (ctx.startswith("contingency") and not kinds):
            raise ValueError(f"{ctx}: exactly one of {_KINDS}, got {kinds}")
        for k, v in (s.get("do") or {}).items():
            reason = check_schema(k, v)
            if reason:
                raise ValueError(f"{ctx}: {reason}")
        for c in s.get("wait_for", []) + s.get("check", []):
            _check_cond(ctx, c)
        for key in ("on_timeout", "on_fail"):
            if key in s and s[key].get("goto") not in cont:
                raise ValueError(f"{ctx}: {key} goto {s[key].get('goto')!r} is not a contingency")
        if "wait_for" in s and not s.get("within"):
            raise ValueError(f"{ctx}: wait_for needs within")
        if "trim" in s:
            t = s["trim"]
            for k in ("signal", "target", "deadband", "key", "base", "gain", "max_step",
                      "settle_s", "max_moves"):
                if k not in t:
                    raise ValueError(f"{ctx}: trim missing {k!r}")
            reason = check_schema(t["key"], 1.0)   # the key must be a float action
            if reason or t["signal"] not in _INSTRUMENTS:
                raise ValueError(f"{ctx}: trim key/signal invalid: {reason or t['signal']}")

    ids = set()
    for i, s in enumerate(d["steps"]):
        sid = s.get("id", f"#{i}")
        if sid in ids:
            raise ValueError(f"{where}: duplicate step id {sid}")
        ids.add(sid)
        check_step(s, f"{where} step {sid}")
    for cid, s in cont.items():
        check_step(s, f"contingency {where}.{cid}")


def load_procedure(path: data.Resource) -> Procedure:
    raw = yaml.safe_load(data.read_text(path))
    proc = Procedure(id=raw["id"], title=raw["title"], purpose=raw.get("purpose", ""),
                     params=dict(raw.get("params", {}) or {}), raw=raw)
    validate(proc)
    return proc


def load_procedures(paths=None) -> dict[str, Procedure]:
    """All packaged procedures (or the given paths), keyed by id."""
    if paths is None:
        paths = [p for _, p in sorted(data.builtin_procedures().items())]
    procs = [load_procedure(p) for p in paths]
    return {p.id: p for p in procs}


# --------------------------------------------------------------------- runner

@dataclass(frozen=True)
class LogEntry:
    t: float
    proc_id: str
    step_id: str
    text: str
    outcome: str   # started | done | timeout | check_failed | completed | aborted |
                   # not_applicable | trim_incomplete | queued


@dataclass
class _Active:
    proc: Procedure
    d: dict          # filled procedure
    seq: list        # current step sequence (main steps or a contingency)
    i: int = 0
    phase: str = "react"          # react | act | wait | hold | trim
    t_phase: float = 0.0
    moves: int = 0
    in_contingency: bool = False
    contingency_outcome: str = "aborted"


@dataclass
class ProcedureRunner:
    """Closed-loop scripted operator. Call `tick(obs, loops, t)` once per step
    and pass the returned action dict (possibly empty) to `sim.step()`."""

    procedures: dict[str, Procedure]
    streams: object | None = None        # hotwell.rng.StreamBank, for random reaction
    reaction_s: float = 5.0              # fixed delay before each step [s]
    reaction_sigma: float = 0.0          # > 0: lognormal(ln reaction_s, sigma) draws
    log: list[LogEntry] = field(default_factory=list)
    _queue: list = field(default_factory=list)
    _active: _Active | None = None

    @property
    def busy(self) -> bool:
        return self._active is not None or bool(self._queue)

    def start(self, proc_id: str, params: dict | None, t: float) -> None:
        """Request a procedure (queued if another is running)."""
        proc = self.procedures[proc_id]
        validate(proc, params)
        self._queue.append((proc, params or {}))
        if self._active is not None:
            self.log.append(LogEntry(t, proc_id, "-", "queued behind " + self._active.proc.id,
                                     "queued"))

    # .................................................................... helpers
    def _delay(self) -> float:
        if self.reaction_sigma > 0.0 and self.streams is not None:
            g = self.streams.stream("operator")
            return float(math.exp(math.log(self.reaction_s) + self.reaction_sigma * g.normal()))
        return self.reaction_s

    @staticmethod
    def _met(conds: list, obs) -> bool:
        for c in conds:
            if "signal" in c:
                if not _OPS[c["op"]](obs.values[c["signal"]], float(c["value"])):
                    return False
            elif bool(obs.indications.get(c["indication"])) != c["eq"]:
                return False
        return True

    def _note(self, t, step, outcome, text=None):
        a = self._active
        self.log.append(LogEntry(t, a.proc.id, step.get("id", "-"),
                                 text if text is not None else step.get("text", ""), outcome))

    def _goto(self, cid: str, t: float) -> None:
        a = self._active
        s = a.d["contingencies"][cid]
        a.seq, a.i, a.phase, a.t_phase = [dict(s, id=cid)], 0, "react", t + self._delay()
        a.in_contingency, a.contingency_outcome = True, s.get("outcome", "aborted")

    def _advance(self, t: float) -> None:
        a = self._active
        a.i += 1
        a.phase, a.t_phase, a.moves = "react", t + self._delay(), 0

    def _finish(self, t: float, outcome: str) -> None:
        a = self._active
        self.log.append(LogEntry(t, a.proc.id, "-", a.d["title"], outcome))
        self._active = None

    # ....................................................................... tick
    def tick(self, obs, loops: dict, t: float) -> dict:
        """Advance the operator to time t (step-start time) and return the
        actions to submit this step."""
        if self._active is None:
            if not self._queue:
                return {}
            proc, params = self._queue.pop(0)
            d = proc.filled(params)
            self._active = _Active(proc, d, d["steps"], t_phase=t + self._delay())
            if not self._met(d.get("applies_when", []), obs):
                self._finish(t, "not_applicable")
                return {}
            self.log.append(LogEntry(t, proc.id, "-", d["title"], "started"))
        a = self._active
        if a.i >= len(a.seq):
            self._finish(t, a.contingency_outcome if a.in_contingency else "completed")
            return {}
        step = a.seq[a.i]
        if a.phase == "react":
            if t + 1e-9 < a.t_phase:
                return {}
            a.phase, a.t_phase = "act", t
        if "do" in step:
            if a.phase == "act":
                self._note(t, step, "done" if not step.get("wait_for") else "started")
                a.phase, a.t_phase = "wait", t
                if not step.get("wait_for"):
                    self._advance(t)
                return dict(step["do"])
            if self._met(step["wait_for"], obs):
                self._note(t, step, "done")
                self._advance(t)
            elif t - a.t_phase >= float(step["within"]) - 1e-9:
                self._note(t, step, "timeout")
                if "on_timeout" in step:
                    self._goto(step["on_timeout"]["goto"], t)
                else:
                    self._finish(t, "aborted")
            return {}
        if "hold" in step:
            if a.phase == "act":
                a.phase, a.t_phase = "hold", t
                return {}
            if t - a.t_phase >= float(step["hold"]) - 1e-9:
                if self._met(step.get("check", []), obs):
                    self._note(t, step, "done")
                    self._advance(t)
                else:
                    self._note(t, step, "check_failed")
                    if "on_fail" in step:
                        self._goto(step["on_fail"]["goto"], t)
                    else:
                        self._finish(t, "aborted")
            return {}
        if "trim" in step:
            tr = step["trim"]
            if a.phase == "act" or (a.phase == "trim" and t - a.t_phase >= tr["settle_s"] - 1e-9):
                err = obs.values[tr["signal"]] - float(tr["target"])
                if abs(err) <= float(tr["deadband"]):
                    self._note(t, step, "done", f"{step.get('text', '')} (in band after "
                               f"{a.moves} moves)")
                    self._advance(t)
                    return {}
                if a.moves >= int(tr["max_moves"]):
                    self._note(t, step, "trim_incomplete")
                    self._advance(t)
                    return {}
                move = -float(tr["gain"]) * err
                ms = float(tr["max_step"])
                move = max(-ms, min(ms, move))
                a.moves += 1
                a.phase, a.t_phase = "trim", t
                return {tr["key"]: round(float(loops[tr["base"]]) + move, 6)}
            return {}
        if "ack_active" in step:
            active = [aid for aid, st in obs.alarms if st == "active"]
            if not active:
                self._note(t, step, "done")
                self._advance(t)
                return {}
            return {"alarm.ack": active[0]}
        # contingency with no kind (e.g. just a note): record it and move on
        self._note(t, step, "done")
        self._advance(t)
        return {}

    def shift_log(self) -> list[str]:
        """Human-readable operator log lines, HH:MM:SS from t = 0."""
        out = []
        for e in self.log:
            s = int(round(e.t))
            out.append(f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}  {e.proc_id:7s} "
                       f"{e.step_id:22s} {e.outcome:15s} {e.text}")
        return out
