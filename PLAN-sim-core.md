# Steam Plant Simulation Core — Phase 1 Implementation Plan

## 0. Context and objective

This is phase 1 of a larger project: a browser-based simulation of a small steam power
plant with a 1970s-style control panel and an AI operator-assistance agent. **This phase
builds only the headless simulation library.** No web server, no UI, no agent, no
Gymnasium wrapper — those are later phases that consume this library.

The deliverable is an installable Python package (`hotwell`) that can:

1. Initialize a reduced-order steam plant at steady state for a commanded load.
2. Step it deterministically through time under automatic control.
3. Inject scripted casualties (pump trips, sensor faults) via scenario files.
4. Produce believable transient behavior for load steps and a condensate-pump-trip
   casualty, ending either in recovery (if scripted operator actions intervene) or in a
   protective plant trip (if they don't).
5. Expose clean **observation**, **action**, **scenario**, and **protection-table**
   contracts that the future panel and agent will consume.

Point 5 is the real product. The physics components must sit behind stable interfaces so
they can be upgraded later (notably the drum model, see §5.2) without breaking consumers.

**Definition of done:** all acceptance tests in §11 pass, the three canonical scenarios in
§9 run and produce the standard plot set, and `HANDOFF.md` is written per §13.

## 1. Locked design decisions

These are decided. Do not re-litigate them; if one appears genuinely unworkable, stop and
record the problem in `HANDOFF.md` rather than silently changing course.

- **Fixed-step RK4** (classical 4th-order Runge–Kutta), `dt = 0.05 s` (20 Hz). No
  adaptive stepping, no implicit solvers.
- **Hybrid system**: continuous states integrated by RK4; discrete state (pump modes,
  trips, latches, valve-open flags) is **frozen during the four RK4 stage evaluations**
  and updated only at step boundaries by the event layer (§3.2).
- **No fast pressure nodes as ODE states.** Header/line pressures and flows are solved as
  a small quasi-static algebraic network inside the derivative function (§5.6). ODE states
  are reserved for slow storage: inventories, energies, rotor speed, actuator positions.
  This avoids stiffness entirely at 20 Hz.
- **Determinism**: identical seed + scenario + platform ⇒ bit-identical trajectories.
  All randomness flows from one `numpy.random.Generator` owned by the simulator.
- **SI units internally** everywhere (Pa, kg, kg/s, J, K, W, rad/s). Display conversions
  (psig, °F, inches of water, Hz, MW) are a later, separate layer. Constants and
  docstrings state units.
- **Controllers and protection act on *sensed* values**, not truth (§8). This makes
  sensor-fault casualties work with no extra machinery.
- **Plain Python + numpy.** Runtime deps: `numpy`, `scipy`, `pyyaml` only. Dev deps:
  `pytest`, `ruff`, `matplotlib` (scripts only, never imported by the package).
- **No frameworks**: no acausal/graph component system, no units library, no pydantic, no
  plugin architecture, no async, no numba/Cython. Explicit wiring in one `Plant` class.
- Python ≥ 3.11, `src/` layout, stdlib `dataclasses` for parameters and specs.

## 2. Plant configuration and reference design point

Fictional single-boiler saturated-steam plant (no superheater — deliberately, this is the
naval-plant lineage), islanded electrical operation.

Equipment: one drum boiler (drum + risers + downcomers treated as one lumped component),
one turbine-generator, one condenser with hotwell, one deaerator (DA) serving as the
feedwater reservoir, two condensate pumps (CP-1, CP-2), two feed pumps (FP-1, FP-2), a
feedwater regulating valve, a turbine throttle/governor valve, boiler firing, and two
electrical load blocks (vital and non-vital) on the islanded bus.

Pumps are **2 × 100%** in each service: one running, one standby. (A 2 × 50% variant is a
future scenario option; make rated fraction a per-pump parameter.)

Reference design point (self-consistent to ~2%; verify with the audit in §10 and record
achieved values in `HANDOFF.md`):

| Quantity | Value | Note |
|---|---|---|
| Rated electrical output | 60 MW | |
| Generator rating | 75 MVA, 60 Hz, 2-pole equiv. | islanded |
| Drum pressure (nominal) | 8.0 MPa | Tsat ≈ 295 °C |
| Steam flow at rated load | ≈ 77 kg/s | from w_spec below |
| Turbine specific work `w_spec` | ≈ 780 kJ/kg | ≈ isentropic Δh (8 MPa sat → 7 kPa) × 0.80 |
| Firing heat at rated load | ≈ 180 MW | ṁ_s · (h_g(8 MPa) − h_fw) |
| Condenser pressure | 7 kPa nominal | algebraic, §5.4 |
| Deaerator pressure | 0.15 MPa | Tsat ≈ 111 °C ⇒ h_fw ≈ 467 kJ/kg |
| Inertia constant H | 4 s on 75 MVA | J = 2·H·S / ω₀² |
| Governor droop R | 5% | |
| Load damping k_pf | 1.5 | P_load = P₀(1 + k_pf·Δf/f₀) |

**Sizing rules** (choose volumes/levels to satisfy these, then record achieved values):

- Deaerator working inventory (normal level → low-suction limit) ≥ 60 s of rated feed flow.
- Hotwell working inventory ≥ 45 s of rated condensate flow.
- Drum liquid inventory (normal level → low-low trip) equivalent to 25–60 s of rated
  steam flow with feed lost.
- Governing requirement: the timing targets in §9 override any individual setpoint.

The steam cycle is **closed** in this phase: no makeup, no blowdown, no reserve feed tank
(noted as a deferred addition). Total water inventory is therefore conserved — this is the
basis of the mass audit.

## 3. Architecture

### 3.1 Repository layout

```
hotwell/
  pyproject.toml
  README.md
  HANDOFF.md
  src/hotwell/
    plant.py            # composition root: wires components, owns state registry
    simulator.py        # step loop, RK4, event sequencing, seeding
    state.py            # StateVector: flat ndarray + named slices per component
    steam_properties.py # committed polynomial fits (§5.1)
    components/
      drum.py           # DrumBoiler interface + TwoStateDrum (+ AstromBellDrum in M4)
      turbine.py        # steam chest, mechanical power, rotor/swing
      condenser.py      # condenser (algebraic) + hotwell inventory
      deaerator.py
      pumps.py          # PumpUnit: modes, spin-up, curve, NPSH
      valves.py         # actuator lags, liquid/steam valve flow laws
      loads.py          # vital / non-vital blocks, frequency dependence
    control/
      pid.py            # discrete PI with output limits + anti-windup
      loops.py          # governor, drum level, drum pressure, DA level
    protection/
      interlocks.py     # trip/alarm engine: timers, latching, first-out
      tables.py         # loads YAML protection tables into dataclasses
    sensors.py          # ObservationSpec, sensor models, fault injection
    actions.py          # action schema + validation against current mode
    scenario.py         # scenario loading + event application
    historian.py        # ring buffer, query API, export
    audit.py            # mass/energy closure diagnostics
  configs/baseline.yaml     # plant parameters
  data/protection.yaml      # alarm + trip tables (§7)
  scenarios/*.yaml          # §9
  scripts/
    run_scenario.py         # CLI: scenario in → plots + CSV out
    gen_steam_props.py      # regenerates property fits, documents provenance
  tests/
```

### 3.2 Step sequence (strict order, deterministic)

1. **Apply actions** submitted for this step (validated against current discrete state;
   invalid actions are rejected with a recorded reason, they do not raise).
2. **Controllers update** (discrete-time PI at 20 Hz) using the *previous* step's sensed
   observation → actuator commands.
3. **RK4 integration** of continuous states over `dt` with discrete state and commands
   frozen. The derivative function internally solves the algebraic flow network (§5.6)
   and the drum flash closure (§5.2).
4. **Event layer**: evaluate alarm/trip conditions on the new state (with per-condition
   time delays), latch trips, run mode transitions (e.g. `starting → running`), apply
   safety-valve hysteresis, record first-out ordering.
5. **Sensors sample truth** → apply active fault modes, range clamp, quantization →
   observation dict.
6. **Historian records**; audit accumulators update.

`Simulator.step(actions) -> Observation` runs this once. A convenience
`run(until, action_script)` loops it.

## 4. State

### 4.1 Continuous states (≈ 13)

| # | Name | Description | Units |
|---|---|---|---|
| 1 | `fw_valve.x` | feed reg valve position | – (0–1) |
| 2 | `throttle.x` | governor/throttle valve position | – |
| 3 | `firing.x` | firing rate fraction | – |
| 4–5 | `cp1.s`, `cp2.s` | condensate pump speed fractions | – |
| 6–7 | `fp1.s`, `fp2.s` | feed pump speed fractions | – |
| 8 | `drum.M` | drum fluid mass (liquid + steam in drum/riser volume) | kg |
| 9 | `drum.U` | drum fluid internal energy | J |
| 10 | `chest.p` | steam chest pressure | Pa |
| 11 | `rotor.omega` | rotor speed | rad/s |
| 12 | `hotwell.M` | hotwell inventory | kg |
| 13 | `da.M` | deaerator inventory | kg |

(The M4 drum swap replaces #8–9 with the four Åström–Bell states; everything else is
untouched. Design the state registry so a component declares its own state slots.)

### 4.2 Discrete state

Per pump: `stopped | starting | running | tripped` (+ trip reason). Boiler master fuel
trip (MFT) latch. Turbine trip latch. Safety valve open flag. Non-vital load connected
flag. Per-alarm state: `clear | active | acknowledged` (acknowledge is an action; the
panel uses this later). First-out record: ordered list of (t, condition) for the
initiating protective actions. Terminal flag `plant_dead` (MFT + all pumps stopped) —
scenarios end early on it.

## 5. Component specifications

Keep every component file under ~300 lines. Prefer legible engineering approximations
with named constants over cleverness.

### 5.1 Steam properties (`steam_properties.py`)

Committed polynomial fits, no runtime property library. Two families:

- Saturation properties vs **pressure** over 3–12 MPa: `Tsat(p)`, `h_f(p)`, `h_g(p)`,
  `u_f(p)`, `u_g(p)`, `v_f(p)`, `v_g(p)`.
- Saturation pressure vs **temperature** over 30–150 °C: `psat(T)` (for condenser/NPSH
  vapor-pressure calculations).

`scripts/gen_steam_props.py` generates the coefficients from a documented source (either
CoolProp installed ad hoc at generation time, or typed-in standard steam-table points)
and writes the module plus an accuracy report; target ≤ 0.5% error against source points
across the range. Commit the generated coefficients; CoolProp must **not** be a runtime
dependency. Anchor checks in tests: Tsat(8 MPa) = 295 ± 1 °C; Tsat(0.15 MPa) = 111.4 ±
0.5 °C; h_g(8 MPa) = 2758 ± 15 kJ/kg.

### 5.2 Drum boiler (`components/drum.py`)

**Interface (stable across phases):** inputs — effective firing heat `Q_fire`, feed flow
`m_fw`, feed enthalpy `h_fw`, steam flow drawn `m_s` (from throttle valve law); outputs —
drum pressure `p`, drum level `l` (m, relative to normal water level NWL = 0), steam
enthalpy `h_g(p)`.

**Phase-1 model (`TwoStateDrum`):** saturated equilibrium mixture in fixed total volume
`V_d`.

- `dM/dt = m_fw − m_s` and `dU/dt = Q_fire + m_fw·h_fw − m_s·h_g(p)`.
- Closure: find `(p, x)` such that `M·v_mix(p,x) = V_d` and `M·u_mix(p,x) = U`, with
  `v_mix = v_f + x·(v_g − v_f)` etc. Solve the 2×2 with damped Newton, warm-started from
  the previous step (it moves slowly; 2–3 iterations typical). Level from liquid volume
  and drum geometry (cylinder is fine).
- Firing heat lag: `Q_fire = x_firing · Q_max` through the firing actuator state (§5.7);
  add a fixed combustion efficiency constant.

Known, accepted limitation: no shrink/swell inverse response (level moves monotonically
with inventory). Encode the upgrade path as a **skipped test** (§11, T9).

**Phase-1.5 model (M4, optional): `AstromBellDrum`** — the four-state model of Åström &
Bell, "Drum-boiler dynamics," *Automatica* 36 (2000): states are drum pressure, total
water volume, riser exit steam quality, and steam volume under the water surface; use the
parameter table published in the paper (160 MW-class unit) with volumes scaled by the
steam-flow ratio to our design point, and document the scaling in `HANDOFF.md`. Same
interface as above.

### 5.3 Turbine, rotor, governor path (`components/turbine.py`)

- Throttle steam flow (choked approximation): `m_s = k_t · x_throttle · p_drum`, with
  `k_t` calibrated so rated flow occurs at rated pressure and `x ≈ 0.85`.
- Steam chest: `τ_ch · dp_chest/dt = p_drum·x_throttle·c − p_chest` — implement as a
  simple first-order lag between valve-commanded flow and mechanical power, `τ_ch = 0.4 s`.
- Mechanical power: `P_m = w_spec · m_s_chest` (constant specific work, §2).
- Swing equation (islanded): `J·dω/dt = (P_m − P_e)/ω − D_m·(ω − ω₀)`, small mechanical
  damping `D_m`. `P_e` = sum of connected load blocks with frequency dependence (§5.5).
- Overspeed trip closes the throttle (turbine trip latch) at 110% speed.

### 5.4 Condenser and hotwell (`components/condenser.py`)

Condenser pressure **algebraic** in this phase: `p_cond = p_cond0 · f(load)` with a mild
monotone load dependence (or simply constant 7 kPa; parameter choice, document it). An
`air_ingress` parameter (scenario-settable, default 0) raises `p_cond` — hook for the
later condenser-air-leak casualty; no other behavior required yet. Condensing (steam →
hotwell) mass flow equals turbine exhaust flow; condensate temperature = Tsat(p_cond).
Hotwell: `dM/dt = m_exhaust − m_condensate_out`. Condenser heat duty computed for the
energy audit: `Q_cond = m_exhaust·(h_exhaust − h_f(p_cond))` with
`h_exhaust = h_g(p_drum) − w_spec`.

### 5.5 Loads (`components/loads.py`)

Two blocks on the islanded bus: vital (always connected while the plant lives) and
non-vital (connectable/sheddable by action or by underfrequency protection). Each:
`P = P₀·(1 + k_pf·(f − f₀)/f₀)`. Rated split ≈ 20% vital / 80% non-vital.

### 5.6 Pumps, flow network, NPSH (`components/pumps.py`, `components/valves.py`)

- Pump head: `H = H₀·s² − K_p·Q²` (s = speed fraction). Shutoff head ≈ 1.25 × rated head.
  Spin-up/coast-down: `τ_p · ds/dt = s_cmd − s`, `τ_p ≈ 3 s` (condensate), `≈ 4 s` (feed);
  `s_cmd ∈ {0, 1}` from the mode machine.
- Liquid valve: `Q = C_v · x · sqrt(max(Δp, 0))`.
- Flow network, quasi-static, solved inside the derivative function:
  - Condensate path: hotwell → CP-1/CP-2 (parallel) → DA level-control valve → DA.
    Pump curves + line resistance + valve resistance ⇒ solve for path flow (scalar
    Newton or closed form for the quadratic case; warm-start).
  - Feed path: DA → FP-1/FP-2 (parallel) → feed reg valve → drum (back-pressure =
    drum pressure + static head). Same solve.
  - Parallel identical pumps at equal speed share flow equally; a stopped pump's branch
    contributes zero flow (check valve assumed).
- NPSH: `NPSH_avail = (p_suction − psat(T_fluid))/(ρg) + z_static`; feed-pump
  `NPSH_req(Q) = a + b·Q²`. Margin `< 0.5 m` sustained 5 s ⇒ pump trip (protection
  table); while margin `< 0`, degrade delivered head by a smooth factor (cavitation).
  Feed-pump suction comes from DA pressure + elevation head; this is what makes a
  draining DA eventually kill the feed pumps.

### 5.7 Actuators (`components/valves.py`)

First-order lags with rate and travel limits: feed reg valve `τ = 2 s`, throttle
`τ = 1 s` (governor actuator), firing `τ = 5 s`. Positions are the continuous states;
commands come from controllers or manual-mode actions.

## 6. Control loops (`control/`)

All PI (no derivative), discrete at 20 Hz, output-limited, with back-calculation
anti-windup. Each loop has `auto | manual` mode; in manual, the operator action sets the
actuator command directly. Tuning: choose gains for smooth, oscillation-free response to
the M3 scenarios; document chosen gains and a one-line rationale each in `HANDOFF.md`.
Loops:

| Loop | PV (sensed) | Output | Notes |
|---|---|---|---|
| Governor | shaft speed / frequency | throttle command | droop law: `x_cmd = load_ref/P_rated − (1/R)·(f − f₀)/f₀`, then actuator lag. Pure droop: islanded frequency offset under load change is expected and correct. `load_ref` is an operator action. |
| Drum level | drum level | feed valve command | single-element PI in phase 1; three-element (level + steam-flow feedforward + feed-flow trim) behind a config flag in M4 |
| Drum pressure | drum pressure | firing command | |
| DA level | DA level | DA level-control valve | keeps the condensate path matched to feed demand; hotwell floats between alarms |

## 7. Protection and alarms (`protection/`, `data/protection.yaml`)

**Data-driven**: one YAML file declares every alarm and trip — signal name, comparison,
setpoint, time delay, latching, and action. The engine is generic. This table is a
first-class contract: the panel's annunciator and the agent's recommendation validator
will read the same file later.

Initial table (values are starting points; the §9 timing targets govern tuning):

| ID | Condition | Delay | Action |
|---|---|---|---|
| `DRUM_LVL_LO` | level < −150 mm | 2 s | alarm |
| `DRUM_LVL_LOLO` | level < −300 mm | 1 s | **MFT + turbine trip** |
| `DRUM_LVL_HI` / `HIHI` | > +150 / +300 mm | 2 / 1 s | alarm / turbine trip |
| `DRUM_P_HI` | p > 8.4 MPa | 2 s | alarm |
| `SAFETY_VALVE` | p > 8.6 MPa open, reseat 8.3 MPa | – | relief flow (capacity ≥ rated steam flow), hysteresis in event layer |
| `DRUM_P_LO` | p < 7.2 MPa | 5 s | alarm |
| `FREQ_LO` / `FREQ_HI` | f < 59.5 / > 60.5 Hz | 2 s | alarm |
| `UF_SHED` | f < 58.8 Hz | 1 s | shed non-vital load |
| `UF_TRIP` | f < 57.0 Hz | 2 s | turbine trip (islanded blackout if firing also lost) |
| `OVERSPEED` | ω > 110% | 0 s | turbine trip |
| `FP_SUCTION` | NPSH margin < 0.5 m | 5 s | trip that feed pump |
| `CP/FP_OVERLOAD` | scenario-injected | – | trip that pump |
| `HOTWELL_LO/HI`, `DA_LO/HI` | level bands | 5 s | alarms |
| `COND_P_HI` | p_cond > 12 kPa | 5 s | alarm (trip variant deferred) |

Trips latch and require an explicit `reset` action after the condition clears. MFT kills
firing; turbine trip slams the throttle. First-out ordering is recorded whenever any
trip-class condition fires.

## 8. Sensors, observation contract, action contract

### 8.1 Sensors (`sensors.py`)

`ObservationSpec`: for each instrument — name, units, range (min/max), display
resolution, description. Initial instrument list (≈ 20): drum pressure, drum level,
steam flow, feed flow, condensate flow, chest pressure, condenser pressure, hotwell
level, DA level, DA pressure, frequency, MW output, per-pump motor current proxy
(∝ hydraulic power) and breaker status, valve position indications, firing rate.

Sensor model per instrument: truth → optional active fault → clamp to range → quantize
to resolution. Fault modes in this phase: `stuck` (holds last value) and `bias` (additive
offset), both scenario-settable per instrument with start/end times. **Controllers and
protection consume sensed values** (protection may optionally use separate "protection
channel" sensors later; not now).

`Observation`: `t`, flat `dict[str, float]` of sensed values, list of active alarm
states, discrete indications (pump run lights, breaker/trip flags — these are honest in
phase 1), and `plant_dead`.

### 8.2 Actions (`actions.py`)

Namespaced command dict, validated against current mode; invalid commands are recorded
and ignored (never raise mid-run). Initial set:

```
{"cp1.start": true}            {"fp2.stop": true}
{"governor.load_ref_mw": 42.0} {"loads.nonvital.connect": false}
{"loop.drum_level.mode": "manual"}
{"fw_valve.manual_cmd": 0.55}  {"firing.manual_cmd": 0.4}
{"alarm.ack": "DRUM_LVL_LO"}   {"trips.reset": true}
```

One schema module documents every key, its type, bounds, and validity conditions. This
schema is the panel's switch list and the agent's tool surface later — keep it boring
and explicit.

## 9. Scenario system and canonical scenarios

Scenario YAML: name, seed, initial condition (load, mode), timed event list, end
condition. Event types in this phase: `trip_pump`, `inhibit_start` (blocks a pump from
starting, for "standby fails to start"), `sensor_fault` (stuck/bias), `set_air_ingress`,
and `action` (scripted operator action — this is how recovery runs are expressed
headlessly).

```yaml
name: cp1_trip_recovered
seed: 42
init: {load_mw: 60, mode: islanded}
events:
  - {t: 300.0, type: trip_pump, target: cp1, reason: overload}
  - {t: 312.0, type: action, command: {"cp2.start": true}}
end: {max_t: 1800}
```

Canonical scenarios (committed, used by tests and plots):

1. **`load_step.yaml`** — 60 MW steady, at t = 300 s non-vital block steps +10% of rated.
   Expect droop response: f settles ≈ 0.3 Hz low (R = 5%), drum pressure/level transients
   damp out, no alarms beyond transient frequency-low.
2. **`cp1_trip_unrecovered.yaml`** — CP-1 trips at t = 300 s, no operator action, CP-2
   auto-start absent (default). Expected cascade: condensate flow lost → DA drains
   (hotwell rises) → feed-pump NPSH margin erodes → FP trips → drum level falls →
   `DRUM_LVL_LOLO` MFT. **Timing target: first protective trip 45–120 s after the pump
   trip**, with the DA buffer consuming most of that window. First-out must identify the
   true initiator.
3. **`cp1_trip_recovered.yaml`** — same, but CP-2 started by scripted action ~12 s after
   the trip. Expect NPSH margin dips but no trip; all levels return to bands; steady
   state re-established within 300 s.

Auto-standby (`auto_start: on|off` per pump pair, default **off**) exists as a config
flag but is off in all canonical scenarios — starting the standby is the operator's job;
that's the game.

## 10. Historian and audit

- `historian.py`: preallocated ring buffers; record every step (20 Hz) with a
  configurable retention (default: full rate for the trailing 10 min, 1 Hz decimated for
  the full run). Query API: `query(signals, t0, t1, max_points) -> (t_array, values)`
  with simple decimation. Export to CSV/NPZ. This API is the future strip-chart feed and
  agent historian tool — keep it free of simulator imports.
- `audit.py`: (a) mass closure — total water inventory (drum + hotwell + DA + a fixed
  piping-holdup constant) must be conserved except integrated safety-valve relief; report
  drift as % of total inventory per hour. (b) energy closure at steady state —
  `Q_fire_effective − (P_e + Q_cond + declared losses)` as % of firing. `plant.audit()`
  returns both; `run_scenario.py` prints them at end of run.

## 11. Acceptance tests (the gate)

All via `pytest`; numeric tolerances stated here are the contract.

- **T1 property anchors**: §5.1 checks pass.
- **T2 steady state**: `initialize_steady_state(load_mw=60)` (scipy root on the
  derivative function with loops in auto) yields ‖derivatives‖ below tolerance; then a
  600 s run drifts each state < 1% of its nominal span, no alarms.
- **T3 mass audit**: over that 600 s run, inventory drift < 0.5% total inventory.
- **T4 energy audit**: steady-state closure residual < 2% of firing heat.
- **T5 determinism**: two runs of `cp1_trip_recovered` (same seed) produce identical
  state-history hashes.
- **T6 droop**: `load_step` settles within 5% of the analytic Δf = −R·ΔP/P_rated·f₀.
- **T7 casualty (unrecovered)**: `cp1_trip_unrecovered` produces MFT via
  `DRUM_LVL_LOLO`, first trip in the 45–120 s window, correct first-out.
- **T8 casualty (recovered)**: `cp1_trip_recovered` completes with zero trips and
  returns to steady bands within 300 s of the standby start.
- **T9 (skipped until M4) inverse response**: with `AstromBellDrum`, a step *increase* in
  steam demand initially *raises* drum level (swell) before it falls. Marked
  `pytest.mark.skip(reason="phase 1.5 drum")` — this test encodes the upgrade gate.
- **T10 sensor fault**: bias fault on drum level sensor drives the (single-element) level
  loop to over/under-feed in the expected direction; protection responds to sensed value.
- **T11 performance**: 1 h simulated in ≤ 60 s wall on a typical laptop core.
- **T12 action validation**: starting an already-running pump, or manual commands while a
  loop is in auto, are rejected-and-recorded, not raised.

`scripts/run_scenario.py <scenario> --plots out/` must produce a standard PNG set: drum
level + pressure, frequency + MW, all four flows, inventories, valve positions, alarm/
trip timeline strip. These plots are the human "believability" check.

## 12. Milestones

Each milestone ends with: tests green, a short `HANDOFF.md` update, small focused
commits. Do not start the next milestone with the previous one red.

- **M0 — skeleton + properties.** Package scaffolding, `steam_properties` + generator
  script + T1. StateVector/registry. Empty component interfaces.
- **M1 — closed loop at steady state.** All components (two-state drum), flow network,
  controllers, `initialize_steady_state`, audit. T2–T4 pass. Deliver a `steady_state.py`
  script printing the balance sheet (flows, powers, closure).
- **M2 — events, scenarios, sensors, historian.** Protection engine + YAML tables, pump
  mode machines, scenario loader, sensor layer with faults, historian, determinism. T5,
  T10, T12 pass.
- **M3 — canonical casualties + plots.** The three scenarios tuned to the timing
  targets; plotting script; T6–T8, T11 pass. **This is the phase-1 finish line.**
- **M4 — optional, on explicit go-ahead only.** `AstromBellDrum` (un-skip T9),
  three-element feedwater option, brief comparison plot of the two drums on
  `load_step.yaml`.

## 13. Working agreements for the implementer

- **Ask-vs-decide**: for ambiguities not covered here, prefer the simplest deterministic
  choice, note it in `HANDOFF.md` under "Decisions taken," and move on. Stop and ask only
  if a locked decision (§1) seems unworkable or two requirements conflict.
- **No silent physics fudging**: if a scenario can't hit its timing target by tuning the
  declared sizing parameters, document what you observed rather than inventing new
  physics or hidden constants.
- **`HANDOFF.md` structure** (kept current; this is the artifact Alan carries to the
  next planning session): Status summary · How to run (env, tests, scenarios) · Test
  results table · Achieved casualty timings vs targets · Reference-design-point achieved
  values · Parameter/tuning decisions and rationale · Decisions taken under ask-vs-decide
  · Known issues / rough edges · Questions for Alan · Notes for the panel phase (anything
  learned about the observation/action contracts).
- Style: `ruff` clean, type hints on public APIs, docstrings state units, component files
  ≲ 300 lines. No dependency additions without a `HANDOFF.md` note explaining why.

## 14. Explicitly out of scope (phase 1)

Web server, UI, WebSocket, panel graphics. Agent, LangGraph, any LLM calls. Gymnasium
wrapper (but keep `step()` free of global state so wrapping stays trivial). Superheater,
reheat, extraction heaters, makeup/blowdown, reserve feed tank. Multi-machine grid /
infinite bus (islanded only). Display-unit conversion layer. Sound, scoring,
randomized-parameter campaigns. Performance work beyond T11.
