"""M2 gate: T5 determinism, T10 sensor faults, T12 action validation,
plus protection-engine and historian unit coverage."""
import numpy as np

from hotwell import data
from hotwell.protection.interlocks import ProtectionEngine
from hotwell.protection.tables import load_protection_table
from hotwell.scenario import load_scenario
from hotwell.simulator import Simulator

SCEN = data.builtin_scenarios()["cp1_trip_recovered"]


def make_sim(load_mw=60.0, seed=0):
    sim = Simulator(seed=seed)
    sim.initialize_steady_state(load_mw)
    return sim


# ------------------------------------------------------------------ T5

def test_t5_determinism():
    hashes = []
    for run in range(2):
        sim = Simulator.from_scenario(SCEN)
        sim.run(420.0)  # covers trip at 300 s + recovery start
        hashes.append(sim.state_history_hash)
        print(f"run {run}: t={sim.t:.2f}s hash={hashes[-1][:16]}...")
    assert hashes[0] == hashes[1]


# ------------------------------------------------------------------ T10

def test_t10_level_bias_drives_underfeed():
    """+50 mm bias on the level sensor: loop sees high, underfeeds, true
    level falls."""
    sim = make_sim()
    sim.sensors.faults["drum_level"] = __import__(
        "hotwell.sensors", fromlist=["SensorFault"]).SensorFault(
        kind="bias", bias=0.05, t_start=0.0)
    true_levels = []
    for _ in range(int(120 / sim.dt)):
        sim.step()
        true_levels.append(sim.last_aux.drum_level)
    print(f"true drum level after 120 s with +50 mm sensed bias: "
          f"{true_levels[-1] * 1e3:.1f} mm (sensed "
          f"{sim.last_obs.values['drum_level'] * 1e3:.1f} mm)")
    assert true_levels[-1] < -0.030  # underfeed drove true level well low


def test_t10_protection_acts_on_sensed_not_truth():
    """A -350 mm bias makes the SENSED level cross LOLO while truth is normal:
    protection must trip on the sensed value."""
    sim = make_sim()
    from hotwell.sensors import SensorFault
    sim.sensors.faults["drum_level"] = SensorFault(kind="bias", bias=-0.35,
                                                   t_start=0.0)
    for _ in range(int(5 / sim.dt)):
        sim.step()
        if sim.disc.mft:
            break
    print(f"MFT={sim.disc.mft} at t={sim.t:.2f}s, true level "
          f"{sim.last_aux.drum_level * 1e3:.1f} mm, first_out={sim.engine.first_out}")
    assert sim.disc.mft
    assert sim.engine.first_out[0][1] == "DRUM_LVL_LOLO"
    assert abs(sim.last_aux.drum_level) < 0.05  # truth was fine


def test_stuck_sensor_holds_value():
    sim = make_sim()
    from hotwell.sensors import SensorFault
    v0 = sim.last_obs.values["drum_pressure"]
    sim.sensors.faults["drum_pressure"] = SensorFault(kind="stuck", t_start=0.0)
    sim.step({"governor.load_ref_mw": 55.0})
    for _ in range(200):
        sim.step()
    assert sim.last_obs.values["drum_pressure"] == v0


# ------------------------------------------------------------------ T12

def test_t12_action_validation():
    sim = make_sim()
    n0 = len(sim.rejected)
    # starting an already-running pump
    sim.step({"cp1.start": True})
    # manual command while loop in auto
    sim.step({"fw_valve.manual_cmd": 0.5})
    # unknown key and out-of-bounds value
    sim.step({"bogus.key": 1})
    sim.step({"governor.load_ref_mw": 500.0})
    rejects = sim.rejected[n0:]
    for r in rejects:
        print(f"rejected @{r.t:.2f}s: {r.action} — {r.reason}")
    assert len(rejects) == 4
    assert "not stopped" in rejects[0].reason
    assert "in auto" in rejects[1].reason
    assert "unknown action" in rejects[2].reason
    assert "outside" in rejects[3].reason
    # valid manual path works after mode switch
    sim.step({"loop.drum_level.mode": "manual"})
    sim.step({"fw_valve.manual_cmd": 0.5})
    assert len(sim.rejected) == n0 + 4
    assert sim.control.drum_level.mode == "manual"
    assert sim.control.drum_level.manual_cmd == 0.5


def test_t12_start_inhibited_and_stop_stopped():
    sim = make_sim()
    sim.disc.start_inhibited.add("cp2")
    sim.step({"cp2.start": True})
    assert "inhibited" in sim.rejected[-1].reason
    sim.step({"fp2.stop": True})
    assert "not running" in sim.rejected[-1].reason


# ------------------------------------------------- protection engine units

def test_engine_delay_and_latch():
    eng = ProtectionEngine(load_protection_table())
    sensed = {c.signal: 0.0 for c in eng.table.conditions}
    # nominal values that trip nothing
    nominal = dict(drum_level=0.0, drum_pressure=8.0e6, frequency=60.0,
                   fp1_npsh_margin=3.0, fp2_npsh_margin=9.0, hotwell_level=0.0,
                   cp1_npsh_margin=1.0, cp2_npsh_margin=1.0,  # 0.4.0 M5b
                   da_level=0.0, cond_pressure=7.0e3)
    sensed.update(nominal)
    assert eng.evaluate(0.0, sensed) == []
    # drum level low: alarm after 2 s, not before
    sensed["drum_level"] = -0.2
    for i in range(41):
        eng.evaluate(0.05 * i, sensed)
    states = dict(eng.alarm_states())
    assert states.get("DRUM_LVL_LO") == "active"
    # clears when condition clears (non-latching)
    sensed["drum_level"] = 0.0
    eng.evaluate(2.5, sensed)
    assert "DRUM_LVL_LO" not in dict(eng.alarm_states())
    # LOLO latches and fires mft+turbine_trip once
    sensed["drum_level"] = -0.35
    fired = []
    for i in range(30):
        fired += eng.evaluate(3.0 + 0.05 * i, sensed)
    kinds = sorted(f.action for f in fired)
    assert kinds == ["mft", "turbine_trip"]
    sensed["drum_level"] = 0.0
    eng.evaluate(10.0, sensed)
    assert dict(eng.alarm_states()).get("DRUM_LVL_LOLO") == "active"  # latched
    assert eng.first_out[0][1] == "DRUM_LVL_LOLO"


def test_engine_safety_valve_hysteresis():
    eng = ProtectionEngine(load_protection_table())
    sensed = dict(drum_level=0.0, drum_pressure=8.7e6, frequency=60.0,
                  fp1_npsh_margin=3.0, fp2_npsh_margin=9.0, hotwell_level=0.0,
                  cp1_npsh_margin=1.0, cp2_npsh_margin=1.0,  # 0.4.0 M5b
                  da_level=0.0, cond_pressure=7.0e3)
    fired = eng.evaluate(0.0, sensed)
    assert [(f.action, f.value) for f in fired] == [("safety_valve", True)]
    sensed["drum_pressure"] = 8.4e6  # above reseat: stays open
    assert eng.evaluate(0.05, sensed) == []
    sensed["drum_pressure"] = 8.2e6  # below reseat: closes
    fired = eng.evaluate(0.10, sensed)
    assert [(f.action, f.value) for f in fired] == [("safety_valve", False)]


def test_ack_and_reset():
    sim = make_sim()
    from hotwell.sensors import SensorFault
    sim.sensors.faults["hotwell_level"] = SensorFault(kind="bias", bias=0.8,
                                                      t_start=0.0)
    for _ in range(int(6 / sim.dt)):
        sim.step()
    assert dict(sim.last_obs.alarms).get("HOTWELL_HI") == "active"
    sim.step({"alarm.ack": "HOTWELL_HI"})
    assert dict(sim.last_obs.alarms).get("HOTWELL_HI") == "acknowledged"
    # ack of a clear alarm is rejected
    sim.step({"alarm.ack": "DA_LO"})
    assert "no active alarm" in sim.rejected[-1].reason


# ----------------------------------------------------------- historian

def test_historian_roundtrip():
    sim = make_sim()
    for _ in range(400):  # 20 s
        sim.step()
    h = sim.historian
    t, vals = h.query(["drum_pressure", "mw_out"], 0.0, 20.0, max_points=100)
    assert 0 < len(t) <= 100
    assert abs(vals["mw_out"][-1] - 60.0e6) < 1.0e6
    t_all, _ = h.query(["drum_pressure"], -np.inf, np.inf, max_points=10 ** 6)
    print(f"query returned {len(t)} decimated / {len(t_all)} full points")
    assert len(t_all) == 401  # init sample + 400 steps


def test_scenario_loader_validates():
    sc = load_scenario(SCEN)
    assert sc.name == "cp1_trip_recovered"
    assert sc.seed == 42
    assert sc.events[0].type == "trip_pump"
    assert sc.events[1].params["command"] == {"cp2.start": True}
    assert np.isclose(sc.max_t, 900.0)
