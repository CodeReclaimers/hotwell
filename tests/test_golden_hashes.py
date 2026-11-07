"""0.4.0 M0 — golden-hash gate.

Every 0.4.0 milestone except M2 (the deliberate physics change) must leave
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

M2 re-pins the values on purpose; the commit that does so must say why.
"""
import pytest

from hotwell import data
from hotwell.plant import load_config
from hotwell.scenario import load_scenario
from hotwell.simulator import Simulator

FIDELITIES = {
    "two_state_1e": ("two_state", False),
    "astrom_bell_3e": ("astrom_bell", True),
}

# (fidelity, scenario) -> (steps, state_history_hash, observation_hash)
GOLDEN = {
    ("two_state_1e", "cp1_trip_unrecovered"): (
        8546,
        "2747189ef192feec66f20965e9b13665c84873fa88ae36e490c433ad4b7890be",
        "c830e181cd969f2c8415bc04bc578673f29b2ec5f3e4e44bf0e4bd8726b870f1"),
    ("two_state_1e", "cp1_trip_recovered"): (
        18000,
        "892d62826d702d6485643d3c6e177e38f1d35c80ee956b7f457c973b09558d6a",
        "366452f623b65b1f6ca944af532cd536d21d8f3e884dbed088667f0a61f5c8c6"),
    ("two_state_1e", "load_step"): (
        18000,
        "20a7aae2e85dba718f8ab3325d4c603c1c046e6af2df02d9998e9e8a5a15fa58",
        "931a255a57cab68f6f85f7fb6f545e5c3b245abcc230d5b163c2f23fb82faa27"),
    ("astrom_bell_3e", "cp1_trip_unrecovered"): (
        10458,
        "5d4c8ed27b0f92c0bd250eb0cca2ab388e2f9fddcc1ec7940a4a3ab8ebb81f3d",
        "7dd6e518257296440348d1e087279e116043de3e9888a8f0d908addd37e413d0"),
    ("astrom_bell_3e", "cp1_trip_recovered"): (
        18000,
        "bb47b9ea951ff6eb2ef7a1ab3121f98fcff99d787442b7390d23b7f0a5fed03e",
        "53c8d6946e78bdbce15d44a35be7cc345c4da26a2a2d44fefcfa37a9cb1f5355"),
    ("astrom_bell_3e", "load_step"): (
        18000,
        "0fb8701ea8ea97afa4fcdfe1f549bccee7b21beecaa710858e8082bdf14d4754",
        "ebccdbcdec7e2d7749d4a493deb206b22f77c87df7a24d933f5bd3d8b3aaee6e"),
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
