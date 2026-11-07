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

AB + 3E entries RE-PINNED IN M4b (2026-11-07), deliberately: three-element
level-trim retune kp 15/ki 0.15 -> kp 30/ki 0.075 (the AB slow level mode was
unstable; HANDOFF 0.4.0 M4b). The two_state + 1E entries are unchanged (that
loop doesn't use the trim), checked by diffing scripts/golden_hashes.py output.

Observation goldens RE-PINNED IN M5b (2026-11-07): OBSERVATION_SPEC grew by 4
instruments (makeup_flow, makeup_valve_pos, cp1/cp2_npsh_margin). All six STATE
goldens and step counts are unchanged: gate G1, the makeup valve stays exactly
closed in every canonical scenario.
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
        "f4c4cccdb0288ad6c06a1e0d6cedda598c15cf89c414d98308ddc80ac169bef7"),
    ("two_state_1e", "cp1_trip_recovered"): (
        18000,
        "dcd1b3a5290214940b80fa1ad34aea220d996637d35c4b1b8803b0ff3911439a",
        "a6c98287cc8056b4c2f5aa906e9548e4fab33efdd8fbb996f678d08f2d097921"),
    ("two_state_1e", "load_step"): (
        18000,
        "ac2199cc8b0b51a603464933c78cff344a18a6ff042c2949161f9d40ff5352d4",
        "028653f2de48e94ca50f6500ea6706f5096a78bcbf415648d8855b0e40aac12a"),
    ("astrom_bell_3e", "cp1_trip_unrecovered"): (
        10468,
        "4079cb8c94c05e9e39588a6292007db68918c4d0e2013d76703bf55ddc0ec5d9",
        "96dea09f42f7ccaa56b593257c64be7874c7e86e6ce497da5de4d3e11315f3fb"),
    ("astrom_bell_3e", "cp1_trip_recovered"): (
        18000,
        "fc970dbee00475701add99d62730cce6f714918ee8ed5a5bb4e593a6abb43d31",
        "9a300b5425692c51c3afe597bb9310010b79ffd29bef52007e1db590035821eb"),
    ("astrom_bell_3e", "load_step"): (
        18000,
        "35aae16396f4cf023be94f07029346b35e87466cc977900833b3273b317b31df",
        "d6386717605138b006af1e8780707828de4fd257b82a113972287271d6916dcb"),
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
