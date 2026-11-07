# 04 Protection and alarms

Each condition below watches one **sensed** instrument. It becomes active when
its inequality has held continuously for the stated delay, and clears when it
stops holding, unless it is **latching**, in which case it stays in until
`trips.reset` after the condition clears. Alarms go active (flashing), then
acknowledged (steady) after `alarm.ack`.
<!-- src: src/hotwell/protection/interlocks.py::ProtectionEngine -->

## Protection table
<!-- BEGIN GENERATED: protection -->
| Id | Window legend | Condition (sensed) | Delay | Latching | Action |
|---|---|---|---|---|---|
| `DRUM_LVL_LO` | DRUM LEVEL / LOW | `drum_level` < -0.15 m (< -5.9 in) | 2 s | no | alarm only |
| `DRUM_LVL_LOLO` | DRUM LEVEL / LOW LOW | `drum_level` < -0.3 m (< -11.8 in) | 1 s | yes | master fuel trip, turbine trip |
| `DRUM_LVL_HI` | DRUM LEVEL / HIGH | `drum_level` > 0.15 m (> 5.9 in) | 2 s | no | alarm only |
| `DRUM_LVL_HIHI` | DRUM LEVEL / HIGH HIGH | `drum_level` > 0.3 m (> 11.8 in) | 1 s | yes | turbine trip |
| `DRUM_P_HI` | DRUM PRESS / HIGH | `drum_pressure` > 8.4 MPa (> 1204 psig) | 2 s | no | alarm only |
| `SAFETY_VALVE` | SAFETY VALVE / OPEN | `drum_pressure` > 8.6 MPa (> 1233 psig) | 0 s | no | safety valve lifts; reseats 8.30 MPa |
| `DRUM_P_LO` | DRUM PRESS / LOW | `drum_pressure` < 7.2 MPa (< 1030 psig) | 5 s | no | alarm only |
| `FREQ_LO` | BUS FREQ / LOW | `frequency` < 59.5 Hz | 2 s | no | alarm only |
| `FREQ_HI` | BUS FREQ / HIGH | `frequency` > 60.5 Hz | 2 s | no | alarm only |
| `UF_SHED` | UNDERFREQ / LOAD SHED | `frequency` < 58.8 Hz | 1 s | no | shed non-vital load |
| `UF_TRIP` | UNDERFREQ / TURB TRIP | `frequency` < 57 Hz | 2 s | yes | turbine trip |
| `OVERSPEED` | TURBINE / OVERSPEED | `frequency` > 66 Hz | 0 s | yes | turbine trip |
| `FP1_SUCTION` | FP-1 SUCTION / LOW NPSH | `fp1_npsh_margin` < 0.5 m (< 1.6 ft) | 5 s | yes | trip FP-1 |
| `FP2_SUCTION` | FP-2 SUCTION / LOW NPSH | `fp2_npsh_margin` < 0.5 m (< 1.6 ft) | 5 s | yes | trip FP-2 |
| `CP1_SUCTION` | CP-1 SUCTION / LOW NPSH | `cp1_npsh_margin` < 0.25 m (< 0.8 ft) | 5 s | yes | trip CP-1 |
| `CP2_SUCTION` | CP-2 SUCTION / LOW NPSH | `cp2_npsh_margin` < 0.25 m (< 0.8 ft) | 5 s | yes | trip CP-2 |
| `HOTWELL_LO` | HOTWELL LVL / LOW | `hotwell_level` < -0.5 m (< -19.7 in) | 5 s | no | alarm only |
| `HOTWELL_HI` | HOTWELL LVL / HIGH | `hotwell_level` > 0.5 m (> 19.7 in) | 5 s | no | alarm only |
| `DA_LO` | DA LEVEL / LOW | `da_level` < -0.5 m (< -19.7 in) | 5 s | no | alarm only |
| `DA_HI` | DA LEVEL / HIGH | `da_level` > 0.5 m (> 19.7 in) | 5 s | no | alarm only |
| `COND_P_HI` | COND PRESS / HIGH | `cond_pressure` > 12 kPa (< 26.4 inHg vac) | 5 s | no | alarm only |
| `COND_P_HIHI` | COND PRESS / HIGH HIGH | `cond_pressure` > 18 kPa (< 24.6 inHg vac) | 5 s | yes | turbine trip |
<!-- END GENERATED: protection -->

## What the trips do

- **Master fuel trip (MFT):** firing goes to zero at once (separate fuel trip
  valve), and the firing demand is held at zero while the trip is latched.
- **Turbine trip:** the throttle slams shut (separate stop valve) and the
  generator breaker opens. The bus is dead: both load blocks and every pump
  motor drop. With MFT also latched and every pump stopped, the plant is
  shut down.
- **Pump trip:** that pump stops; there is **no automatic start of the
  standby pump**.
- **Underfrequency load shed:** the non-vital block is disconnected.
- **Safety valve:** lifts at its setpoint and reseats only below a lower
  pressure (hysteresis).
<!-- src: src/hotwell/simulator.py::Simulator._apply_protective_actions -->
<!-- src: src/hotwell/simulator.py::Simulator._do_mft -->

## First-out record

The first-out record lists, in order, the first condition or external event
behind each trip, so the **initiator** of a cascade can be identified. It
includes events with no window of their own: a pump tripped on overload
appears as, for example, `CP1_TRIP:overload`, and the manual pushbuttons as
`MANUAL_MFT` and `MANUAL_TURBINE_TRIP`. Always start a post-trip review from
the first entry.
<!-- src: src/hotwell/protection/interlocks.py::ProtectionEngine.record_external_trip -->
