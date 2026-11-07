# 01 Plant description

## Overview and flow path

Saturated steam leaves the boiler drum, passes the turbine throttle (governor)
valve and the steam chest, and expands through the turbine to the condenser.
Condensate collects in the condenser hotwell. A condensate pump (CP-1 or CP-2)
lifts it through the DA level-control valve (DA LCV) into the deaerator (DA).
There a draw of **pegging steam** taken directly from the drum heats it to
saturation at the DA's fixed pressure. A feed pump (FP-1 or FP-2) takes
suction from the DA and returns it through the feed regulating valve (FRV) to
the drum.
<!-- src: src/hotwell/plant.py::Plant.deriv -->

There is no superheater, reheat, or extraction heating. The cycle is closed:
apart from the drum safety valve, a leak, or makeup from the storage tank,
water neither enters nor leaves.
<!-- src: src/hotwell/plant.py::Plant.total_water_mass -->

The generator is the only source on its bus. The bus carries a **vital** load
block, a **non-vital** load block (which can be shed), and the plant's own
pump motors (station service). There is no outside grid and no other
station-service supply. A turbine trip opens the generator breaker, the bus
goes dead, and every pump motor stops.
<!-- src: src/hotwell/simulator.py::Simulator._do_turbine_trip -->
<!-- src: src/hotwell/components/loads.py::Loads.p_elec -->

## Systems

**Boiler and drum.** Firing heat goes to the drum/riser circuit. Drum pressure
is held by the boiler master (drum pressure loop moving the firing rate).
Drum level depends on the water inventory *and*, under the Åström–Bell
model, on the steam volume below the water surface. A sudden rise in steam
demand makes level **swell** before it falls, and a reduction in cold
feedwater makes level **rise**, because less condensation of steam bubbles
leaves more steam under the surface. Operators should expect level to move
the "wrong way" for the first minute or two after a demand or feed change on
that model.
<!-- src: src/hotwell/components/drum.py::AstromBellDrum.derivatives -->

**Turbine, generator and governor.** The throttle valve sets steam flow; the
steam chest adds a short lag. Specific work depends on drum pressure and on
condenser pressure (an isentropic expansion into the condenser), so a worse
condenser vacuum costs electrical output. At rated, the loss is about
1.4 % of turbine work per kPa of condenser pressure.
<!-- src: src/hotwell/components/turbine.py::isentropic_drop -->
<!-- src: scripts/steady_state.py::main (prints dw/dp_cond) -->
The governor is pure droop (5 %). With the load reference fixed, more load
means lower frequency; the operator restores 60 Hz by moving the load
reference (NOP-03).
<!-- src: src/hotwell/control/loops.py::ControlSystem.governor_cmd -->

**Condenser and hotwell.** Condenser pressure rises with exhaust flow
(heat load), plus any air in-leakage. The hotwell level moves with the
difference between the turbine exhaust condensing into it, the condensate
pumped out of it, and any makeup water drawn in.
<!-- src: src/hotwell/components/condenser.py::Condenser.p_cond -->

**Makeup.** A condensate storage tank (CST) at atmospheric pressure feeds a
makeup valve into the condenser; the condenser vacuum draws the water in, and
condensing steam heats it to the hotwell temperature. The hotwell level loop
opens the makeup valve only when the hotwell falls below its low setpoint,
which sits below normal operating variation. In normal operation the valve
is **closed** and makeup flow is zero, so **any steady makeup flow means the
cycle is losing water** (AOP-09). There is no reject path: makeup can add
water but not remove it.
<!-- src: src/hotwell/plant.py::Plant.deriv -->
<!-- src: src/hotwell/control/loops.py::ControlSystem.update -->

**Condensate system.** Two 100 % condensate pumps in parallel; one normally
runs. The DA level loop positions the DA LCV to hold DA level, which sets
condensate flow. The condensate pumps' suction margin (NPSH) falls one-for-one
with hotwell level, and each pump trips if its margin stays low.

**Deaerator.** Fixed pressure, saturated. Its storage is the buffer between
the condensate and feed systems: losing all condensate flow drains it, and
the feed pumps' suction margin (NPSH) falls with DA level.
<!-- src: src/hotwell/components/deaerator.py::Deaerator.m_pegging -->

**Feedwater system.** Two 100 % feed pumps in parallel; one normally runs. The
drum level loop positions the FRV. Neither pump starts automatically: a
standby pump runs only when an operator starts it.
<!-- src: src/hotwell/simulator.py::Simulator._apply_one -->

## Design point
<!-- BEGIN GENERATED: design_point -->
| Quantity (rated, 60 MW) | SI | Customary |
|---|---|---|
| Electrical output (gross, incl. station service) | 60.000 MW |  |
| Station service (running pump motors) | 1040.7 kW |  |
| Bus frequency | 60.00 Hz |  |
| Drum pressure | 8.000 MPa | 1146 psig |
| Drum saturation temperature | 295.1 °C | 563 °F |
| Main steam (turbine) flow | 76.92 kg/s | 611 klb/hr |
| Pegging steam to the deaerator | 10.20 kg/s | 81 klb/hr |
| Feedwater flow | 87.12 kg/s | 691 klb/hr |
| Condensate flow | 76.92 kg/s | 611 klb/hr |
| Makeup flow (normally zero) | 0.00 kg/s | 0 klb/hr |
| Effective firing heat to fluid | 199.6 MW |  |
| Condenser pressure | 7.00 kPa abs | 27.9 inHg vac |
| Condenser duty | 139.6 MW |  |
| Deaerator pressure (fixed) | 150 kPa abs | 7.1 psig |
| Turbine specific work / derived efficiency | 780.0 kJ/kg / 0.7991 |  |
| Throttle / feed reg valve / firing / DA LCV position | 0.8500 / 0.5528 / 0.8009 / 0.5999 |  |
| FP-1 NPSH margin | 2.70 m | 8.8 ft |
| CP-1 NPSH margin | 1.00 m | 3.3 ft |
| Total water inventory | 27.81 t |  |
<!-- END GENERATED: design_point -->

## Equipment data
<!-- BEGIN GENERATED: equipment -->
| Equipment | Data (baseline config) |
|---|---|
| Condensate pumps (CP-1, CP-2), 2 x 100 % | 0.0775 m³/s service; shutoff head 50 m; 40 m at service flow; motor 40 kW; rated current 60 A |
| Feed pumps (FP-1, FP-2), 2 x 100 % | 0.0916 m³/s service; shutoff head 1117 m; 962 m at service flow; motor 1000 kW; rated current 400 A |
| Turbine | throttle k_t 1.1312e-05 kg/(s·Pa), rated position 0.85, specific work 780 kJ/kg at design, steam chest lag 0.4 s |
| Generator / rotor | 75 MVA, H = 4.0 s, 60 Hz, 2-pole (3600 rpm) |
| Condenser / hotwell | 5.5 kPa at zero exhaust + 1.5 kPa at rated exhaust; hotwell area 8.0 m², nominal level 1.0 m above bottom, 3.0 m above CP suction |
| Deaerator | fixed 150 kPa abs; area 3.0 m², nominal level 2.5 m, 11.0 m above FP suction |
| Drum (two-state model) | 28.0 m³ total, 14.0 m³ liquid at NWL, waterplane 16.0 m² |
| Firing | 280 MW fuel at 100 %, combustion efficiency 0.89 |
| Makeup (CST → condenser) | tank at atmospheric pressure, 30 °C, 5.0 m above the condenser inlet; makeup valve passes 10 kg/s wide open at design vacuum (drawn in by the condenser vacuum); no reject path |
| Drum safety valve | lifts 8.60 MPa (1233 psig), reseats 8.30 MPa (1189 psig) |
| Actuator: fw_valve | lag 2.0 s, max slew 0.2 /s |
| Actuator: throttle | lag 1.0 s, max slew 1.0 /s |
| Actuator: firing | lag 5.0 s, max slew 0.1 /s |
<!-- END GENERATED: equipment -->
