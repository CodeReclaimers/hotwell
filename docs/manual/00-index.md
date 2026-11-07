# hotwell plant manual

Plant description and operator manual for the **hotwell** simulated power
plant: a fictional 60 MW, single-boiler, saturated-steam plant running
islanded (one generator feeding its own bus). It is written for two readers:
a human operator at the hotwell-panel control board, and a software agent
reading plant data or operating the plant through the simulator's action
interface.

| Chapter | Contents |
|---|---|
| [01 Plant description](01-plant-description.md) | systems, flow path, design point, equipment data |
| [02 Instrumentation](02-instrumentation.md) | every instrument, its range and resolution; status lamps |
| [03 Controls](03-controls.md) | control loops, operator controls, the action list |
| [04 Protection](04-protection.md) | alarms, trips and the first-out record |
| [05 Normal operating procedures](05-normal-procedures.md) | pump swaps, frequency trim, alarm acknowledgement |
| [06 Alarm response](06-alarm-response.md) | one section per annunciator window |
| [07 Abnormal operating procedures](07-abnormal-procedures.md) | symptom-based responses to plant upsets |
| [08 Model limitations](08-model-limitations.md) | what the simulator does not model |

## Conventions

- **Units.** SI throughout, with US customary in parentheses in the
  generated tables, using the same conversions as the control board
  (`src/hotwell/units.py`). Pressures are absolute in SI. The condenser is
  shown as **vacuum** in customary units (inHg vac, higher is better), so a
  *rising* condenser pressure is a *falling* vacuum.
- **Levels** are relative: drum level to normal water level (NWL), deaerator
  (DA) and hotwell levels to their nominal operating levels. Negative is low.
- **Sensed values.** Every instrument reading, every controller and every
  protection condition uses *sensed* values: true value, then any instrument
  fault, then measurement noise, then clamping to range and rounding to the
  instrument's resolution. A failed transmitter therefore misleads the
  controllers and the protection exactly as it misleads the operator.
- **Tables marked GENERATED** are produced from the simulator's own data by
  `scripts/gen_manual.py`; a test fails if they fall out of date. The prose
  around them is hand-written from the code; HTML comments name the source
  (`path::Symbol`) behind each claim.
- **Fidelity.** The plant runs with one of two drum models: a two-state
  lumped drum with single-element level control (the baseline), or the
  Åström–Bell drum with three-element feedwater control. Where the two behave
  differently in a way an operator would notice, this manual says so.
