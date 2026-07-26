"""T9 — drum shrink/swell inverse response (M4, AstromBellDrum).

With the four-state Astrom-Bell drum, a step INCREASE in steam demand must
initially RAISE drum level (swell) before the inventory effect pulls it
down. The phase-1 TwoStateDrum is monotone in inventory by design (accepted
limitation, plan section 5.2) — verified here as the contrast case.
"""
from hotwell.plant import load_config
from hotwell.simulator import Simulator


def _swell_peak(model: str) -> float:
    """Peak level rise [m] in the 20 s after a +10% steam-demand step."""
    cfg = load_config()
    cfg["drum"]["model"] = model
    sim = Simulator(cfg, seed=0)
    sim.initialize_steady_state(54.0)
    level0 = sim.last_aux.drum_level
    sim.step({"governor.load_ref_mw": 60.0})
    peak = -1.0
    for _ in range(int(20.0 / sim.dt)):
        sim.step()
        peak = max(peak, sim.last_aux.drum_level - level0)
    return peak


def test_t9_swell_on_steam_demand_step():
    peak = _swell_peak("astrom_bell")
    print(f"astrom_bell swell peak after +6 MW load step: {peak * 1e3:+.1f} mm")
    # swell: level must RISE measurably on a demand increase (inverse response).
    # 3 mm is ~an order of magnitude above numeric noise; the observed peak is
    # ~6 mm (softer than the paper's Fig 7 because our step arrives through the
    # droop governor + 1 s throttle actuator under closed-loop level control).
    assert peak > 0.003


def test_two_state_has_no_swell():
    """Contrast: the phase-1 drum must NOT swell (documents the limitation)."""
    peak = _swell_peak("two_state")
    print(f"two_state peak after +6 MW load step: {peak * 1e3:+.1f} mm")
    assert peak < 0.005
