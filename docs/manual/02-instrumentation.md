# 02 Instrumentation

Every value below is **sensed**: the true value, then any instrument fault,
then measurement noise (if configured), then clamped to the instrument's
range and rounded to its resolution. A reading pinned at the end of its range
may be beyond it.
<!-- src: src/hotwell/sensors.py::SensorBank.sample -->

## Instruments
<!-- BEGIN GENERATED: instruments -->
| Instrument | Measures | SI unit | SI range | Resolution | Customary range |
|---|---|---|---|---|---|
| `drum_pressure` | drum pressure | Pa | 0 kPa … 12 MPa | 10 kPa | -15 … 1726 psig |
| `drum_level` | drum level rel. NWL | m | -0.5 m … 0.5 m | 0.001 m | -19.7 … 19.7 in |
| `steam_flow` | main steam (throttle) flow | kg/s | 0 kg/s … 150 kg/s | 0.1 kg/s | 0 … 1190 klb/hr |
| `feed_flow` | feedwater flow to drum | kg/s | 0 kg/s … 150 kg/s | 0.1 kg/s | 0 … 1190 klb/hr |
| `condensate_flow` | condensate flow to DA | kg/s | 0 kg/s … 150 kg/s | 0.1 kg/s | 0 … 1190 klb/hr |
| `chest_pressure` | turbine steam chest pressure | Pa | 0 kPa … 12 MPa | 10 kPa | -15 … 1726 psig |
| `cond_pressure` | condenser pressure | Pa | 0 kPa … 20 kPa | 0.05 kPa | 24.0 … 29.9 inHg vac |
| `hotwell_level` | hotwell level rel. nominal | m | -1 m … 1.5 m | 0.001 m | -39.4 … 59.1 in |
| `da_level` | deaerator level rel. nominal | m | -2.5 m … 0.5 m | 0.001 m | -98.4 … 19.7 in |
| `da_pressure` | deaerator pressure | Pa | 0 kPa … 300 kPa | 1 kPa | -14.7 … 28.8 psig |
| `frequency` | bus/rotor frequency | Hz | 50 Hz … 70 Hz | 0.01 Hz | 50.00 … 70.00 Hz |
| `mw_out` | generator electrical output | W | 0 MW … 80 MW | 0.1 MW | 0.0 … 80.0 MW |
| `cp1_current` | CP-1 motor current (proxy) | A | 0 A … 100 A | 0.5 A | 0 … 100 A |
| `cp2_current` | CP-2 motor current (proxy) | A | 0 A … 100 A | 0.5 A | 0 … 100 A |
| `fp1_current` | FP-1 motor current (proxy) | A | 0 A … 500 A | 1 A | 0 … 500 A |
| `fp2_current` | FP-2 motor current (proxy) | A | 0 A … 500 A | 1 A | 0 … 500 A |
| `fw_valve_pos` | feed reg valve position | - | 0 … 1 | 0.005 | 0 … 100 % |
| `throttle_pos` | throttle valve position | - | 0 … 1 | 0.005 | 0 … 100 % |
| `firing_rate` | firing rate fraction | - | 0 … 1 | 0.005 | 0 … 100 % |
| `da_lcv_pos` | DA level control valve position | - | 0 … 1 | 0.005 | 0 … 100 % |
| `fp1_npsh_margin` | FP-1 NPSH margin | m | -5 m … 15 m | 0.05 m | -16.4 … 49.2 ft |
| `fp2_npsh_margin` | FP-2 NPSH margin | m | -5 m … 15 m | 0.05 m | -16.4 … 49.2 ft |
| `makeup_flow` | CST makeup flow to condenser | kg/s | 0 kg/s … 20 kg/s | 0.1 kg/s | 0 … 159 klb/hr |
| `makeup_valve_pos` | makeup valve position | - | 0 … 1 | 0.005 | 0 … 100 % |
| `cp1_npsh_margin` | CP-1 NPSH margin | m | -5 m … 15 m | 0.05 m | -16.4 … 49.2 ft |
| `cp2_npsh_margin` | CP-2 NPSH margin | m | -5 m … 15 m | 0.05 m | -16.4 … 49.2 ft |
<!-- END GENERATED: instruments -->

Two derived quantities are not instruments of their own. Shaft speed is
read off `frequency` (2-pole, 60 Hz = 3600 rpm). Saturation temperatures
follow from the pressures.

## Status lamps (always truthful)

| Indication | Meaning |
|---|---|
| `cp1_running`, `cp2_running`, `fp1_running`, `fp2_running` | pump running (a starting pump reads running once it reaches 95 % speed) |
| `cp1_tripped`, `cp2_tripped`, `fp1_tripped`, `fp2_tripped` | pump tripped (by protection, overload or a dead bus) |
| `mft` | master fuel trip latched |
| `turbine_trip` | turbine tripped (throttle shut, breaker open) |
| `safety_valve_open` | drum safety valve lifted |
| `nonvital_connected` | non-vital load block on the bus |
| `breaker_closed` | generator breaker closed (bus alive) |
<!-- src: src/hotwell/simulator.py::Simulator._indications -->
<!-- src: src/hotwell/simulator.py::Simulator._event_layer -->

Lamps are never faulted. If an instrument disagrees with a lamp, believe the
lamp.
