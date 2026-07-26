"""T9 — drum shrink/swell inverse response. SKIPPED until the M4 AstromBellDrum.

This test encodes the phase-1.5 upgrade gate: with the four-state Astrom-Bell
drum model, a step INCREASE in steam demand must initially RAISE drum level
(swell) before it falls. The phase-1 TwoStateDrum is monotone in inventory by
design (accepted limitation, plan section 5.2) and cannot pass this.
"""
import pytest

from hotwell.simulator import Simulator


@pytest.mark.skip(reason="phase 1.5 drum (AstromBellDrum, M4) — TwoStateDrum has no swell")
def test_t9_swell_on_steam_demand_step():
    sim = Simulator(seed=0)
    sim.initialize_steady_state(54.0)
    level0 = sim.last_aux.drum_level
    # step steam demand up ~10% via the governor load reference
    sim.step({"governor.load_ref_mw": 60.0})
    peak = -1.0
    for _ in range(int(10.0 / sim.dt)):
        sim.step()
        peak = max(peak, sim.last_aux.drum_level - level0)
    # swell: level must rise measurably before the inventory effect pulls it down
    assert peak > 0.005  # m
