"""0.4.0 M6: procedures as data, the background-operator runner, and the
replay-exact action recorder."""
import numpy as np
import pytest

from hotwell.plant import load_config
from hotwell.procedures import ProcedureRunner, load_procedure, load_procedures
from hotwell.recorder import ActionRecorder, drive
from hotwell.rng import StreamBank
from hotwell.scenario import Scenario, ScenarioEvent, load_scenario
from hotwell.simulator import Simulator

PROCS = load_procedures()


def _sim(events=(), max_t=900.0, cfg=None, seed=1):
    sc = Scenario("m6", seed, 60.0, "islanded", tuple(sorted(events, key=lambda e: e.t)), max_t)
    sim = Simulator(cfg or load_config(), scenario=sc)
    sim.initialize_steady_state(60.0)
    return sim


def _outcomes(runner):
    return [(e.proc_id, e.step_id, e.outcome) for e in runner.log]


def test_packaged_procedures_load_and_validate():
    print(f"\nprocedures: {sorted(PROCS)}")
    assert sorted(PROCS) == ["NOP-01", "NOP-02", "NOP-03", "NOP-04"]
    # templating fills both directions and every action key passes check_schema
    for pid in ("NOP-01", "NOP-02"):
        for a, b in (("1", "2"), ("2", "1")):
            p = pid[-1] == "1" and "cp" or "fp"
            d = PROCS[pid].filled({"from": f"{p}{a}", "to": f"{p}{b}"})
            assert list(d["steps"][0]["do"]) == [f"{p}{b}.start"]
            assert "{" not in d["title"]


@pytest.mark.parametrize(("pid", "a", "b"), [("NOP-01", "cp1", "cp2"), ("NOP-02", "fp1", "fp2")])
def test_swap_and_swap_back_complete_cleanly(pid, a, b):
    sim = _sim(max_t=900.0)
    r = ProcedureRunner(PROCS)
    drive(sim, 900.0, r, [(10.0, pid, {"from": a, "to": b}), (400.0, pid, {"from": b, "to": a})])
    print("\n" + "\n".join(r.shift_log()))
    outs = [o for _, s, o in _outcomes(r) if s == "-"]
    assert outs == ["started", "completed", "started", "completed"]
    assert sim.disc.pump_modes[a] == "running" and sim.disc.pump_modes[b] == "stopped"
    assert not sim.rejected
    assert sim.last_obs.alarms == []


def test_swap_meets_inhibited_standby_and_aborts_safely():
    sim = _sim([ScenarioEvent(0.0, "inhibit_start", {"target": "cp2"})], max_t=200.0)
    r = ProcedureRunner(PROCS)
    drive(sim, 200.0, r, [(10.0, "NOP-01", {"from": "cp1", "to": "cp2"})])
    print("\n" + "\n".join(r.shift_log()) + f"\nrejected {[(x.t, x.reason) for x in sim.rejected]}")
    assert ("NOP-01", "start_standby", "timeout") in _outcomes(r)
    assert ("NOP-01", "-", "aborted") in _outcomes(r)
    assert sim.disc.pump_modes["cp1"] == "running"
    assert [x.reason for x in sim.rejected] == ["cp2 start inhibited"]
    assert sim.last_obs.alarms == []


def test_not_applicable_when_preconditions_fail():
    sim = _sim(max_t=30.0)
    r = ProcedureRunner(PROCS)
    drive(sim, 30.0, r, [(1.0, "NOP-02", {"from": "fp2", "to": "fp1"})])
    assert _outcomes(r) == [("NOP-02", "-", "not_applicable")]
    assert not sim.rejected


def test_frequency_trim_restores_60_hz():
    """+3 MW on the non-vital block at t = 10 s: droop leaves f ~0.14 Hz low.
    NOP-03 trims the load reference until sensed f is within 60 +- 0.02 Hz."""
    sim = _sim([ScenarioEvent(10.0, "set_load", {"target": "nonvital", "p0": 50.17e6})],
               max_t=900.0)
    r = ProcedureRunner(PROCS)
    drive(sim, 120.0)
    f_before = sim.last_obs.values["frequency"]
    drive(sim, 900.0, r, [(120.0, "NOP-03", {})])
    trim = [e for e in r.log if e.step_id == "trim"]
    print("\n" + "\n".join(r.shift_log()) + f"\nf before trim {f_before:.2f} Hz, after "
          f"{sim.last_obs.values['frequency']:.2f} Hz; load_ref "
          f"{sim.loop_state()['load_ref_mw']:.3f} MW")
    assert f_before < 59.9
    assert trim and trim[-1].outcome == "done"
    assert abs(sim.last_obs.values["frequency"] - 60.0) <= 0.02 + 1e-9


def test_alarm_acknowledge_procedure():
    """A hotwell-level transmitter bias lights HOTWELL_HI (5 s delay). No loop
    acts on that reading here, so the window stays lit; NOP-04 acknowledges it."""
    sim = _sim([ScenarioEvent(1.0, "sensor_fault",
                              {"target": "hotwell_level", "kind": "bias", "bias": 0.6})],
               max_t=60.0)
    r = ProcedureRunner(PROCS, reaction_s=1.0)
    drive(sim, 8.0)
    assert ("HOTWELL_HI", "active") in sim.last_obs.alarms
    drive(sim, 15.0, r, [(8.0, "NOP-04", {})])
    print(f"\nalarms {sim.last_obs.alarms}; log {_outcomes(r)}; rejected {sim.rejected}")
    assert sim.last_obs.alarms == [("HOTWELL_HI", "acknowledged")]
    assert _outcomes(r) == [("NOP-04", "-", "started"), ("NOP-04", "ack", "done"),
                            ("NOP-04", "-", "completed")]
    assert not sim.rejected


# ------------------------------------------------------------------ recorder

def _replay(scenario, cfg=None, n_steps=None):
    sim = Simulator(cfg or load_config(), scenario=scenario)
    sim.initialize_steady_state(scenario.load_mw)
    for _ in range(n_steps):
        sim.step()
    return sim


def test_recorded_run_replays_bit_identically_including_same_tick_collision(tmp_path):
    """Scenario events, the operator's actions, and a same-tick collision (a
    scenario action and a submitted action setting the SAME key on the SAME
    tick: live order is event-then-action, so 62 MW must win) all reduce to one
    scenario that replays to identical state and observation hashes, through a
    YAML round trip."""
    events = [ScenarioEvent(5.0, "action", {"command": {"governor.load_ref_mw": 61.0}}),
              ScenarioEvent(30.0, "set_load", {"target": "nonvital", "p0": 50.17e6})]
    sim = _sim(events, max_t=700.0)
    rec = ActionRecorder(sim)
    while sim.t < 5.0 - 0.025:
        rec.step()
    rec.step({"governor.load_ref_mw": 62.0, "alarm.ack": "NOPE"})   # same tick as the event
    assert sim.loop_state()["load_ref_mw"] == 62.0
    r = ProcedureRunner(PROCS)
    drive(sim, 700.0, r, [(40.0, "NOP-03", {}), (60.0, "NOP-01", {"from": "cp1", "to": "cp2"})],
          recorder=rec)
    n = int(round(sim.t / sim.dt))
    path = rec.to_yaml(tmp_path / "rec.yaml")
    rep = _replay(load_scenario(path), n_steps=n)
    print(f"\nrecorded {len(rec.records)} records over {n} steps; live state "
          f"{sim.state_history_hash[:16]} replay {rep.state_history_hash[:16]}; obs "
          f"{sim.observation_hash[:16]} / {rep.observation_hash[:16]}; rejections live "
          f"{len(sim.rejected)} replay {len(rep.rejected)}")
    assert rep.state_history_hash == sim.state_history_hash
    assert rep.observation_hash == sim.observation_hash
    assert [x.reason for x in rep.rejected] == [x.reason for x in sim.rejected]


def test_random_reaction_is_reproducible_and_leaves_plant_streams_alone():
    cfg = load_config()
    cfg["sensors"]["noise"] = {"drum_level": {"sigma": 0.003}}
    runs = []
    for sigma in (0.0, 0.4, 0.4):
        sim = _sim(cfg=cfg, max_t=400.0, seed=9)
        r = ProcedureRunner(PROCS, streams=sim.streams, reaction_s=5.0, reaction_sigma=sigma)
        z = []
        sched = [(10.0, "NOP-01", {"from": "cp1", "to": "cp2"})]
        pending = list(sched)
        while sim.t < 400.0 - 0.025:
            if pending and pending[0][0] <= sim.t + 1e-9:
                r.start(*pending.pop(0)[1:], sim.t)
            sim.step(r.tick(sim.last_obs, sim.loop_state(), sim.t) or None)
            z.append(sim.sensors.last_draws.copy())
        runs.append(([(round(e.t, 2), e.step_id, e.outcome) for e in r.log], np.array(z)))
    (log0, z0), (log1, z1), (log2, z2) = runs
    print(f"\nfixed-delay step times {[t for t, *_ in log0][:4]}; "
          f"random {[t for t, *_ in log1][:4]}")
    assert log1 == log2                         # reproducible from the seed
    assert log1 != log0                         # the random delays actually differ
    assert np.array_equal(z0, z1) and np.array_equal(z1, z2)   # I2: sensor streams untouched


@pytest.mark.parametrize(("body", "msg"), [
    ("steps:\n  - {id: a, text: x, do: {'bogus.key': true}}", "unknown action key"),
    ("steps:\n  - {id: a, text: x, hold: 5, check: [{signal: nope, op: gt, value: 1}]}",
     "unknown instrument"),
    ("steps:\n  - {id: a, text: x, do: {'cp2.start': true}, wait_for: "
     "[{indication: cp2_running, eq: true}], within: 5, on_timeout: {goto: missing}}",
     "not a contingency"),
    ("steps:\n  - {id: a, text: x, hold: 5, do: {'cp2.start': true}}", "exactly one of"),
])
def test_malformed_procedures_fail_at_load(tmp_path, body, msg):
    p = tmp_path / "bad.yaml"
    p.write_text(f"id: BAD\ntitle: bad\n{body}\ncontingencies: {{}}\n")
    with pytest.raises(ValueError, match=msg):
        load_procedure(p)


def test_runner_never_touches_streams_when_reaction_is_fixed():
    bank = StreamBank(1)
    r = ProcedureRunner(PROCS, streams=bank)
    assert r._delay() == 5.0 and "operator" not in bank._streams
