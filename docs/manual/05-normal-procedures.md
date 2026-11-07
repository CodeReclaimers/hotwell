# 05 Normal operating procedures

These procedures are stored as data (`src/hotwell/data/procedures/`). The
same files produce this chapter **and** drive the simulator's scripted
background operator, so what is written here is exactly what that operator
does. Pump names appear as parameters: `<from>` is the pump in service and
`<to>` the one being brought in. Each procedure works in either direction.
Before each step the operator allows a short reaction time.
<!-- src: src/hotwell/procedures.py::ProcedureRunner -->
<!-- BEGIN GENERATED: procedures -->
### NOP-01 — Condensate pump swap (<from> running -> <to>)

Transfer condensate duty from the running condensate pump to the standby pump without interrupting flow to the deaerator.

Parameters: `<from>` (e.g. `cp1`), `<to>` (e.g. `cp2`).

**Applies when:** `<from>_running` is on; `<to>_running` is off; `<to>_tripped` is off.

**Steps**

1. **Start <to>. Confirm the run lamp and motor current.**
   - Action: `<to>.start` = true
   - Expect within 30 s: `<to>_running` is on; `<to>_current` > 20.0. Otherwise go to *standby_failed*.
2. **Run both pumps in parallel for one minute; confirm DA level and both pumps' suction margin.**
   - Wait 60 s, then confirm: `da_level` > -0.3; `condensate_flow` > 20.0; `<to>_npsh_margin` > 0.5; `<from>_npsh_margin` > 0.5. Otherwise go to *stop_new_pump*.
3. **Stop <from>. Confirm the run lamp goes out.**
   - Action: `<from>.stop` = true
   - Expect within 15 s: `<from>_running` is off. Otherwise go to *stop_failed*.
4. **Verify <to> alone holds condensate flow, DA level and hotwell level for two minutes.**
   - Wait 120 s, then confirm: `<to>_running` is on; `da_level` > -0.3; `hotwell_level` < 0.3; `<to>_npsh_margin` > 0.5. Otherwise go to *restore_original*.

**Contingencies**

- *standby_failed*: <to> did not start. Leave <from> in service and report to the shift supervisor. Outcome: aborted.
- *stop_new_pump*: Parallel run unsatisfactory. Stop <to>, leave <from> in service, and report. Action: `<to>.stop` Outcome: aborted.
- *stop_failed*: <from> did not stop. Leave both pumps running and report. Outcome: aborted.
- *restore_original*: <to> alone is not holding. Restart <from> and report. Action: `<from>.start` Outcome: aborted_restored.

### NOP-02 — Feed pump swap (<from> running -> <to>)

Transfer feedwater duty from the running feed pump to the standby pump while holding drum level.

Parameters: `<from>` (e.g. `fp1`), `<to>` (e.g. `fp2`).

**Applies when:** `<from>_running` is on; `<to>_running` is off; `<to>_tripped` is off.

**Steps**

1. **Start <to>. Confirm the run lamp and motor current.**
   - Action: `<to>.start` = true
   - Expect within 30 s: `<to>_running` is on; `<to>_current` > 150.0. Otherwise go to *standby_failed*.
2. **Run both pumps in parallel for one minute; confirm suction margin on both.**
   - Wait 60 s, then confirm: `<to>_npsh_margin` > 1.0; `<from>_npsh_margin` > 1.0. Otherwise go to *stop_new_pump*.
3. **Stop <from>. Confirm the run lamp goes out.**
   - Action: `<from>.stop` = true
   - Expect within 15 s: `<from>_running` is off. Otherwise go to *stop_failed*.
4. **Verify <to> alone holds feed flow and drum level for two minutes.**
   - Wait 120 s, then confirm: `<to>_running` is on; `drum_level` > -0.1; `drum_level` < 0.1. Otherwise go to *restore_original*.

**Contingencies**

- *standby_failed*: <to> did not start. Leave <from> in service and report to the shift supervisor. Outcome: aborted.
- *stop_new_pump*: Parallel run unsatisfactory. Stop <to>, leave <from> in service, and report. Action: `<to>.stop` Outcome: aborted.
- *stop_failed*: <from> did not stop. Leave both pumps running and report. Outcome: aborted.
- *restore_original*: <to> alone is not holding drum level. Restart <from> and report. Action: `<from>.start` Outcome: aborted_restored.

### NOP-03 — Frequency trim (governor load reference)

Restore bus frequency to 60.00 +- 0.02 Hz after a load change by moving the governor load reference in steps of at most 2 MW.

**Applies when:** `breaker_closed` is on.

**Steps**

1. **Move the load reference toward 60.00 Hz, waiting 30 s between moves.**
   - Move `governor.load_ref_mw` by −20 MW per Hz of error (at most 2 MW per move, 30 s apart, up to 20 moves) until `frequency` is within 60 ± 0.02 Hz.

### NOP-04 — Acknowledge active alarms

Acknowledge every flashing annunciator window after reading it. This does not correct the condition; that is the alarm response procedure's job.

**Steps**

1. **Acknowledge each flashing window in turn.**
   - `alarm.ack` each window that is flashing, one at a time.
<!-- END GENERATED: procedures -->
