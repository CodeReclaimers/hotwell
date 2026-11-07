"""0.4.0 M0 — golden-hash gate.

Every 0.4.0 milestone after M2 (the deliberate physics change) must leave
these unchanged (plan invariant I1: a new feature at its default is
bit-identical to the feature not existing).

Provenance: computed 2026-11-07 by scripts/golden_hashes.py run against a
pristine worktree of 9464eb2 (hotwell 0.3.0, the last commit before any 0.4.0
edit). The script ran each scenario with the Simulator.run() stopping rule and
computed the observation hash OUTSIDE the simulator, from the Observation
objects step() returned, so the in-simulator `observation_hash` added in M0 is
checked against an implementation it doesn't share. The command and its
output are recorded in progress-20261107.md.

The two hashes have different sensitivity (mutation check, 2026-11-07): scaling
the drum-level kp by (1 + 1e-7) changed the STATE hash but not the OBSERVATION
hash, because quantization absorbs sub-LSB differences in truth. So the state
hash is the gate for "physics unchanged" and the observation hash is the gate
for "what a consumer saw is unchanged"; neither one substitutes for the other.

Observation goldens re-pinned 2026-11-07 when the encoding gained the alarm
list (Alan's amendment, before M2); the state goldens didn't change.

RE-PINNED IN M2 (2026-11-07), deliberately: backpressure- and inlet-pressure-
dependent turbine work plus the COND_P_HIHI trip is the one hash-breaking
milestone of 0.4.0. Values from `scripts/golden_hashes.py` on the M2 tree (two
identical runs). Before M2 the values were the 0.3.0 ones (9464eb2, see git
history). Every later milestone must leave these unchanged.
"""
import pytest

from hotwell import data
from hotwell.plant import load_config
from hotwell.scenario import Scenario, ScenarioEvent, load_scenario
from hotwell.simulator import Simulator

FIDELITIES = {
    "two_state_1e": ("two_state", False),
    "astrom_bell_3e": ("astrom_bell", True),
}

# (fidelity, scenario) -> (steps, state_history_hash, observation_hash)
GOLDEN = {
    ("two_state_1e", "cp1_trip_unrecovered"): (
        8550,
        "2f2c4a18fc03617cb06f40ec25d18cc063c88879e8bacae942a68fd858c9b66f",
        "7daee8b52cf34eb2113da57ef088b746e3b964458bafe72fb6b5bf9290c55ab0"),
    ("two_state_1e", "cp1_trip_recovered"): (
        18000,
        "dcd1b3a5290214940b80fa1ad34aea220d996637d35c4b1b8803b0ff3911439a",
        "61c3cb8a4bb1f709ec09be32eadfc9e3a4c1f211d7f91f1b665fa1323678e6eb"),
    ("two_state_1e", "load_step"): (
        18000,
        "ac2199cc8b0b51a603464933c78cff344a18a6ff042c2949161f9d40ff5352d4",
        "3791d20afc51aa16e2199aba4731243d5833eeffdd95978da873cd35fea5aa26"),
    ("astrom_bell_3e", "cp1_trip_unrecovered"): (
        10462,
        "c1614e37ffb8ddd8d8bbe92d3c791099d25c93372e68388f2615b97cd6e5df3c",
        "0dc989c19e1df3e2ab8a5f6d3d6bd35c6ee8b416224832a9fbd83f5fc913b17c"),
    ("astrom_bell_3e", "cp1_trip_recovered"): (
        18000,
        "6deb4b0f17a97b7ab15b97bcada94191b801f52d918173c8583bf14bf2ddf189",
        "5da930b13efe0b021c284a9ce0f5e565dd1cd67a265daa0f7aff33fb6fb73e33"),
    ("astrom_bell_3e", "load_step"): (
        18000,
        "01781e1723040415e48ee756387efe93856b3c0a9aaa4d0020fe5b9400b9d206",
        "4880271e46de549490676b5ca16c2f81f0ebebca8e8aba3780f369651fb13df9"),
}


def _run(fidelity: str, scenario: str) -> Simulator:
    model, three_element = FIDELITIES[fidelity]
    cfg = load_config()
    cfg["drum"]["model"] = model
    cfg["control"]["drum_level"]["three_element"] = three_element
    sc = load_scenario(data.builtin_scenarios()[scenario])
    sim = Simulator(cfg, scenario=sc)
    sim.initialize_steady_state(sc.load_mw)
    sim.run()
    return sim


@pytest.mark.parametrize(("fidelity", "scenario"), sorted(GOLDEN))
def test_golden_hashes(fidelity: str, scenario: str):
    steps, state_h, obs_h = GOLDEN[(fidelity, scenario)]
    sim = _run(fidelity, scenario)
    n = int(round(sim.t / sim.dt))
    print(f"\n{fidelity:15s} {scenario:22s} steps {n} (golden {steps}) "
          f"t={sim.t:.2f} dead={sim.disc.plant_dead}\n"
          f"  state {sim.state_history_hash}\n  golden {state_h}\n"
          f"  obs   {sim.observation_hash}\n  golden {obs_h}")
    assert n == steps
    assert sim.state_history_hash == state_h
    assert sim.observation_hash == obs_h


def test_observation_hash_is_deterministic_and_distinct_from_state_hash():
    """Two identical runs agree on both hashes; the two hashes aren't the same
    digest (they cover different byte streams)."""
    a = _run("two_state_1e", "cp1_trip_unrecovered")
    b = _run("two_state_1e", "cp1_trip_unrecovered")
    print(f"\nrun A obs {a.observation_hash}\nrun B obs {b.observation_hash}")
    assert a.observation_hash == b.observation_hash
    assert a.state_history_hash == b.state_history_hash
    assert a.observation_hash != a.state_history_hash


def test_observation_hash_before_any_step_is_empty_digest():
    """initialize_steady_state's observation isn't hashed (same rule as the
    state hash: post-step only)."""
    sim = Simulator(load_config(), seed=0)
    sim.initialize_steady_state(60.0)
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sim.observation_hash == empty
    assert sim.state_history_hash == empty


def test_alarm_ack_reaches_observation_hash_but_not_state_hash():
    """Acknowledging an alarm changes what the operator sees (active ->
    acknowledged) but not the physics. A +0.2 m drum-level bias at t = 1 s
    lights DRUM_LVL_HI (sensed > 0.15 m for 2 s); run B acknowledges it."""
    sc = Scenario(name="ack_probe", seed=0, load_mw=60.0, mode="islanded",
                  events=(ScenarioEvent(1.0, "sensor_fault",
                                        {"target": "drum_level", "kind": "bias",
                                         "bias": 0.2}),),
                  max_t=30.0)
    runs = []
    for ack in (False, True):
        sim = Simulator(load_config(), scenario=sc)
        sim.initialize_steady_state(sc.load_mw)
        acked = False
        while sim.t < 6.0:
            act = None
            if ack and not acked and ("DRUM_LVL_HI", "active") in sim.last_obs.alarms:
                act, acked = {"alarm.ack": "DRUM_LVL_HI"}, True
            sim.step(act)
        print(f"\nack={ack}: alarms {sim.last_obs.alarms} rejected {sim.rejected}"
              f"\n  state {sim.state_history_hash}\n  obs   {sim.observation_hash}")
        runs.append(sim)
    a, b = runs
    assert ("DRUM_LVL_HI", "active") in a.last_obs.alarms
    assert ("DRUM_LVL_HI", "acknowledged") in b.last_obs.alarms
    assert not b.rejected
    assert a.state_history_hash == b.state_history_hash
    assert a.observation_hash != b.observation_hash
