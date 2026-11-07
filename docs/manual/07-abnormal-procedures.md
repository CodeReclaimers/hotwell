# 07 Abnormal operating procedures

Symptom-based. Each procedure starts from what the board shows, not from an
assumed cause. Standby pumps never start by themselves (chapter 01). Every
action named here is in the action list (chapter 03).

## AOP-01 Loss of condensate flow

**Symptoms:** a condensate pump trip lamp, `condensate_flow` falling, DA level
falling, hotwell level rising, feed pump NPSH margin falling.

**Why it matters:** the DA's stored water is all that keeps the feed pump
supplied. With no condensate flow at rated load, the running feed pump trips
on low suction margin after about a minute and a half (about 93 s on the
two-state drum, 78 s on the Åström–Bell drum), and loss of feed follows.
<!-- src: scripts/run_scenario.py::main (cp1_trip_unrecovered --events, both fidelities) -->

1. Start the standby condensate pump (`cp1.start` / `cp2.start`) at once. Starting
   it within the first quarter-minute keeps the feed pumps well clear of their
   trip.
   <!-- src: src/hotwell/data/scenarios/cp1_trip_recovered.yaml (standby start at +12 s; tests/test_m3_casualties.py T8) -->
2. Confirm condensate flow returns and DA level recovers.
3. If no condensate pump can be started: shed the non-vital load
   (`loads.nonvital.connect` = false) and lower the load reference to cut steam
   and feed demand and buy time. Prepare for AOP-02.
4. If the DA LCV is not opening although its controller calls for it, see AOP-05.

## AOP-02 Loss of feedwater

**Symptoms:** a feed pump trip lamp, `feed_flow` falling to zero, drum level
moving (on the Åström–Bell drum it may **rise first**), drum pressure rising,
possibly the safety valve.

1. Start the standby feed pump (`fp1.start` / `fp2.start`) at once and confirm flow.
2. If a feed pump cannot be started: reduce firing and load. Shed the
   non-vital block and lower the load reference. With no feed, a trip on drum
   level is inevitable; if it is imminent, trip manually (`trips.manual_mft`)
   rather than wait.
3. If both feed pumps are available but suction margin is low, the cause is
   upstream: restore DA level (AOP-01).

## AOP-03 Degrading condenser vacuum

**Symptoms:** `cond_pressure` rising (vacuum falling), generator output
falling at constant load reference, frequency sagging, COND_P_HI.

1. Note how condenser pressure moves with load. A rise that grows with load
   points to heat-transfer loss; a rise roughly independent of load points to
   air in-leakage.
2. Reduce load (lower the load reference; shed the non-vital block if
   necessary) to reduce the load-dependent part of condenser pressure.
3. If condenser pressure keeps rising toward the high-high trip, trip the
   turbine manually (`trips.manual_turbine`) in a controlled way rather than
   wait for the trip.
4. Cross-check `cond_pressure` against output and exhaust flow. A reading that
   moves while output does not suggests a transmitter problem.

## AOP-04 Drum level control abnormal (including transmitter failure)

**Symptoms:** drum level alarms, or the level loop moving the FRV in a way
that doesn't match the steam and feed flows.

1. Check the mass balance. At steady drum level, feed flow equals steam flow
   plus the pegging steam to the DA (design point, chapter 01). A level
   reading that holds steady while feed persistently exceeds or falls short of
   steam + pegging means **the reading is wrong** (the controller is holding a
   false reading at setpoint) or the plant is losing water.
2. If the level reading is not credible: put the drum level loop in manual
   (`loop.drum_level.mode` = manual) and set the FRV (`fw_valve.manual_cmd`) to
   hold feed equal to steam + pegging. Watch the flows rather than the level
   reading.
3. Remember that protection also uses the sensed level. A failed transmitter
   can cause a spurious trip, or fail to trip when it should.

## AOP-05 Valve not following its controller

**Symptoms:** a valve position (FRV, DA LCV, throttle, firing) that doesn't
follow its controller's output on the loop station; a valve that stops making
the small moves it normally makes.

1. Compare position with controller output. A growing gap means the valve is
   stuck or slow.
2. Put the loop in manual and try a small manual move. A valve that answers
   in manual was a control problem; one that doesn't is mechanical.
3. Stuck FRV: control drum level with firing and load, and plan a controlled
   shutdown. Stuck DA LCV: watch DA and hotwell levels, and be ready to reduce
   load. Slow throttle: avoid fast load changes, because large frequency
   excursions follow (AOP-06).

## AOP-06 Frequency excursion

**Symptoms:** FREQ_LO or FREQ_HI; in a severe case the underfrequency load
shed or a trip.

1. Small offsets after a load change are normal (droop): trim the load
   reference (NOP-03).
2. Falling toward the load-shed point: shed the non-vital block yourself
   (`loads.nonvital.connect` = false) before the protection does, and find the
   generation shortfall (low drum pressure, low vacuum, throttle).
3. After any load shed or rejection: lower the load reference at once to keep
   the turbine clear of the overspeed trip.

## AOP-07 Safety valve lift

**Symptoms:** SAFETY_VALVE, `safety_valve_open`, drum pressure at the lift
point.

1. Reduce firing: put the drum pressure loop in manual
   (`loop.drum_pressure.mode`) and lower `firing.manual_cmd`.
2. Restore feedwater if it has been lost (AOP-02).
3. Return the pressure loop to auto once pressure is back below the reseat
   point and steady.

## AOP-09 Loss of cycle water

**Symptoms:** hotwell level trending down at steady load with condensate and
DA normal; then, once the hotwell reaches the makeup setpoint, `makeup_flow`
rising from zero and holding steady; at steady drum level, feed flow above
steam flow plus pegging steam (chapter 01); firing slightly higher than usual
for the load.

1. Any steady makeup flow means water is leaving the cycle. Check the safety
   valve lamp first.
2. If the safety valve is shut, the loss is a leak. Estimate its rate from the
   makeup flow (or, before makeup starts, from the hotwell trend: about
   8 t of water per metre of hotwell level).
   <!-- src: src/hotwell/data/baseline.yaml (condenser.a_hotwell) -->
3. If makeup is **not** flowing while the hotwell keeps falling (makeup valve
   not following its controller, AOP-05), the condensate pumps will lose
   suction and trip: reduce load and prepare a controlled shutdown before
   CP1_SUCTION / CP2_SUCTION.
4. A leak large enough to exceed makeup capacity needs a controlled shutdown.

## AOP-08 After a trip

**Symptoms:** `mft` and/or `turbine_trip` lamps; after a turbine trip,
`breaker_closed` off and every pump stopped.

1. Read the first-out record (chapter 04) to find the initiator.
2. Acknowledge the alarms (NOP-04).
3. Correct the cause, then `trips.reset` once the trip conditions have
   cleared. Restarting from a dead plant is not modelled (chapter 08).
