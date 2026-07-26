"""0.2.0 §11.1: operator manual trip pushbuttons.

The contract is that `trips.manual_mft` / `trips.manual_turbine` are identical
in effect to the corresponding protective actions (they invoke the same
`_do_mft` / `_do_turbine_trip`), and that the first-out record identifies the
operator as the initiator via a MANUAL_* label.
"""
from __future__ import annotations

import pytest

from hotwell.actions import ACTION_SCHEMA, check_schema
from hotwell.simulator import Simulator


def make_sim(load_mw=60.0):
    sim = Simulator(seed=0)
    sim.initialize_steady_state(load_mw)
    return sim


def test_actions_are_in_the_schema():
    keys = {s.key for s in ACTION_SCHEMA}
    assert "trips.manual_mft" in keys
    assert "trips.manual_turbine" in keys
    assert check_schema("trips.manual_mft", True) is None
    assert check_schema("trips.manual_turbine", True) is None
    # bool-typed, like the other pushbuttons
    assert "expected bool" in check_schema("trips.manual_mft", 1.0)


def test_manual_mft_kills_firing_and_records_first_out():
    sim = make_sim()
    sim.run(10.0)
    fire_before = sim.last_obs.values["firing_rate"]
    assert fire_before > 0.5, fire_before
    sim.step({"trips.manual_mft": True})
    assert sim.last_obs.indications["mft"] is True
    assert sim.last_obs.values["firing_rate"] == 0.0
    labels = [lbl for _, lbl in sim.engine.first_out]
    assert labels == ["MANUAL_MFT"], labels
    # firing stays dead: the controller command is forced to 0 while latched
    sim.run(sim.t + 20.0)
    assert sim.last_obs.values["firing_rate"] == 0.0
    print(f"\n  firing {fire_before:.3f} -> {sim.last_obs.values['firing_rate']:.3f}; "
          f"first_out={sim.engine.first_out}")


def test_manual_turbine_trip_opens_breaker_and_kills_the_bus():
    """Checklist (e): a manual turbine trip drops the bus dead."""
    sim = make_sim()
    sim.run(10.0)
    assert sim.last_obs.indications["breaker_closed"] is True
    assert sim.last_obs.indications["cp1_running"] is True
    assert sim.last_obs.indications["fp1_running"] is True
    sim.step({"trips.manual_turbine": True})
    ind = sim.last_obs.indications
    assert ind["turbine_trip"] is True
    assert ind["breaker_closed"] is False       # generator breaker opens (D10)
    assert sim.last_obs.values["throttle_pos"] == 0.0
    for p in ("cp1", "cp2", "fp1", "fp2"):      # dead bus drops contactors
        assert ind[f"{p}_running"] is False
    labels = [lbl for _, lbl in sim.engine.first_out]
    assert labels[0] == "MANUAL_TURBINE_TRIP", labels
    assert "CP1_TRIP:bus_dead" in labels        # cascade joins the record
    print(f"\n  breaker open, throttle=0, MW={sim.last_obs.values['mw_out']/1e6:.2f}; "
          f"first_out={labels}")


def test_manual_trip_matches_the_protective_path_exactly():
    """Same discrete state and same state vector as the protective action."""
    manual = make_sim()
    manual.run(10.0)
    manual.step({"trips.manual_mft": True})

    protective = make_sim()
    protective.run(10.0)
    from hotwell.protection.interlocks import FiredAction
    protective._apply_protective_actions(
        [FiredAction(protective.t, "DRUM_LVL_LOLO", "mft")])
    protective.step()

    assert manual.disc.mft == protective.disc.mft is True
    assert manual.last_obs.values["firing_rate"] == \
        protective.last_obs.values["firing_rate"] == 0.0


def test_repeat_press_is_rejected_with_a_reason():
    sim = make_sim()
    sim.run(10.0)
    sim.step({"trips.manual_mft": True})
    n_before = len(sim.rejected)
    sim.step({"trips.manual_mft": True})
    assert len(sim.rejected) == n_before + 1
    assert sim.rejected[-1].reason == "MFT already latched"
    sim.step({"trips.manual_turbine": True})
    sim.step({"trips.manual_turbine": True})
    assert sim.rejected[-1].reason == "turbine already tripped"
    # only one MANUAL_MFT in first-out despite two presses
    assert [lbl for _, lbl in sim.engine.first_out].count("MANUAL_MFT") == 1


def test_false_value_is_a_no_op_not_a_trip():
    """Releasing the pushbutton must not trip anything."""
    sim = make_sim()
    sim.run(10.0)
    sim.step({"trips.manual_mft": False, "trips.manual_turbine": False})
    assert sim.disc.mft is False
    assert sim.disc.turbine_trip is False
    assert sim.rejected == []
    assert sim.engine.first_out == []


def test_manual_mft_then_plant_dead():
    """MFT plus every pump stopped is plant_dead (existing event-layer rule)."""
    sim = make_sim()
    sim.run(10.0)
    sim.step({"trips.manual_turbine": True})   # bus dead trips all pumps
    obs = sim.step({"trips.manual_mft": True})  # then the fuel trip
    assert obs.plant_dead is True
    assert sim.t == pytest.approx(10.1, abs=0.06)
