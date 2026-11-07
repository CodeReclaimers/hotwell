# 08 Model limitations

What the simulator does **not** model. An operator or agent reasoning from
textbook plant behaviour should know where this plant departs from it.

- **Fixed-pressure deaerator; fixed-temperature hotwell and DA.** Both are
  saturated reservoirs at fixed temperature (DA at its fixed pressure, hotwell
  at the condenser saturation temperature). There is no DA pressure transient
  and no subcooling.
  <!-- src: src/hotwell/components/deaerator.py::Deaerator -->
- **No carryover or steam-quality effects** of high drum level. A very high
  level matters only through the high-level alarm and trip.
- **No post-trip heat loss.** After a full trip the isolated drum stays near
  operating pressure.
- **Turbine expansion starts from the drum state.** There is no throttling
  loss across the governor valve and no exhaust (leaving) loss, so the
  sensitivity of output to condenser pressure is the ideal isentropic value
  (higher than large-unit rules of thumb).
  <!-- src: src/hotwell/components/turbine.py::Turbine.specific_work -->
- **Pump speed is independent of bus frequency,** and motors draw no inrush
  current on starting.
- **No cold start, no restart from a dead plant.** Scenarios end when the
  plant is shut down.
- **Status lamps never fail.** Only analog instruments can be faulted.
- **Single islanded generator.** No grid, no other station-service supply, no
  synchronising.
- **Quasi-static hydraulics.** Pump and valve flows are solved algebraically
  each instant; there is no water hammer and no pipe inertia.
  <!-- src: src/hotwell/components/pumps.py::solve_path_flow -->
- **Unlimited makeup, no reject.** The storage tank never runs out and has
  no level of its own; nothing removes excess water from the cycle. A leak
  has no effect on combustion.
- **Condenser pressure is algebraic** in exhaust flow and air in-leakage;
  there is no air-removal (ejector) system to operate.
