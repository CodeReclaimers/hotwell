# 03 Controls

## Control loops
<!-- BEGIN GENERATED: loops -->
| Loop | Measures | Moves | Setpoint | Tuning | Auto/manual |
|---|---|---|---|---|---|
| Governor | sensed frequency | throttle | load reference (operator) | pure droop R = 0.05 | always auto |
| Drum level, single-element | sensed drum level | feed reg valve | 0 m (NWL) | kp 3.0, ki 0.05 | `loop.drum_level.mode` |
| Drum level, three-element (option) | drum level → flow trim; feed flow → valve | feed reg valve | 0 m; demand = steam flow + trim | trim kp 30.0, ki 0.075; flow kp 0.004, ki 0.02 | `loop.drum_level.mode` |
| Drum pressure (boiler master) | sensed drum pressure | firing rate | 8.0 MPa | kp 1.80e-07, ki 3.0e-09 | `loop.drum_pressure.mode` |
| Deaerator level | sensed DA level | DA LCV (direct) | 0 m (nominal) | kp 1.5, ki 0.025 | `loop.da_level.mode` |
| Hotwell level (makeup) | sensed hotwell level | makeup valve (direct) | -0.15 m (below normal; closed in normal operation) | kp 13.0, ki 0.044, conditional anti-windup | `loop.hotwell_level.mode` |
<!-- END GENERATED: loops -->

All loops act on **sensed** values, so a biased transmitter drives its loop to
hold the *reading* at setpoint while the true value moves away. Every loop has
an auto/manual switch. In manual, the operator's command goes straight to the
valve or firing demand and the controller tracks it, so returning to auto is
bumpless.
<!-- src: src/hotwell/control/pid.py::PI -->
<!-- src: src/hotwell/control/loops.py::ControlSystem.update -->

**Three-element feedwater** (optional fidelity): the feed demand is the
sensed steam flow plus a slow level trim, and an inner loop drives the FRV to
make sensed feed flow meet that demand. At steady level, feed flow exceeds
steam flow by the pegging steam drawn to the DA (see the design point in
chapter 01). That offset is normal, not a leak. Because the inner loop chases
feed-flow measurement noise, the FRV is constantly making small moves. A
feed reg valve that stops moving altogether is a sign it may be stuck.
<!-- src: src/hotwell/control/loops.py::ControlSystem._fw_cmd -->

**Hotwell level (makeup).** The loop sits closed in normal operation. It is
built so that a long spell with the hotwell *high* (for example during a
condensate pump outage) does not wind it up: it never opens while the level is
above its setpoint. When it is holding a water loss, makeup flow hunts slightly
around the loss rate, because the loop works off the 1 mm hotwell level
resolution.
<!-- src: src/hotwell/control/pid.py::PI.update -->

**Governor.** Droop only, no integral action. Frequency settles away from
60 Hz after any load change until the operator moves the load reference.

## Operator actions
<!-- BEGIN GENERATED: actions -->
| Action | Type | Bounds | Effect | Accepted when |
|---|---|---|---|---|
| `cp1.start` | bool |  | start pump CP1 | pump stopped, start not inhibited, bus energized |
| `cp2.start` | bool |  | start pump CP2 | pump stopped, start not inhibited, bus energized |
| `fp1.start` | bool |  | start pump FP1 | pump stopped, start not inhibited, bus energized |
| `fp2.start` | bool |  | start pump FP2 | pump stopped, start not inhibited, bus energized |
| `cp1.stop` | bool |  | stop pump CP1 | pump starting or running |
| `cp2.stop` | bool |  | stop pump CP2 | pump starting or running |
| `fp1.stop` | bool |  | stop pump FP1 | pump starting or running |
| `fp2.stop` | bool |  | stop pump FP2 | pump starting or running |
| `governor.load_ref_mw` | float | 0 … 75 | governor load reference [MW] | always (clamped to bounds) |
| `loads.nonvital.connect` | bool |  | connect/shed the non-vital load block | bus energized |
| `loop.drum_level.mode` | str |  | drum level loop auto|manual | always |
| `loop.drum_pressure.mode` | str |  | drum pressure loop auto|manual | always |
| `loop.da_level.mode` | str |  | DA level loop auto|manual | always |
| `fw_valve.manual_cmd` | float | 0 … 1 | feed reg valve manual command | drum_level loop in manual |
| `firing.manual_cmd` | float | 0 … 1 | firing manual command | drum_pressure loop in manual, no MFT |
| `da_lcv.manual_cmd` | float | 0 … 1 | DA level control valve manual command | da_level loop in manual |
| `loop.hotwell_level.mode` | str |  | hotwell level (makeup) loop auto|manual | always |
| `makeup_valve.manual_cmd` | float | 0 … 1 | makeup valve manual command | hotwell_level loop in manual |
| `alarm.ack` | str |  | acknowledge an active alarm by id | alarm active |
| `trips.reset` | bool |  | reset latched trips whose condition has cleared | always |
| `trips.manual_mft` | bool |  | manual master fuel trip pushbutton (covered guard) | MFT not already latched |
| `trips.manual_turbine` | bool |  | manual turbine trip pushbutton (covered guard) | turbine not already tripped |
<!-- END GENERATED: actions -->

An action that isn't valid in the plant's present state (for example,
starting a pump that is already running, or giving a manual valve command
while its loop is in auto) is **rejected with a reason** and has no effect.
<!-- src: src/hotwell/simulator.py::Simulator._apply_one -->

## Trips and reset

`trips.manual_mft` and `trips.manual_turbine` are the covered manual trip
pushbuttons; their effect is identical to the protective trips. `trips.reset`
clears latched trips **whose condition has cleared**. The generator breaker
recloses if the turbine trip cleared, and tripped pumps return to stopped
(restartable) unless their own trip is still latched.
<!-- src: src/hotwell/simulator.py::Simulator._manual_trip -->
<!-- src: src/hotwell/simulator.py::Simulator._do_reset -->
