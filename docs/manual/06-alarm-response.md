# 06 Alarm response

One section per annunciator window. The first line of each (GENERATED) is
the exact condition from the protection table; the rest is guidance.
*Probable causes* are what usually produces the symptom in this plant. They
are a starting point for diagnosis, not a complete list.

## DRUM_LVL_LO

<!-- BEGIN GENERATED: arp_DRUM_LVL_LO -->
**Window:** DRUM LEVEL / LOW · **Condition:** `drum_level` < -0.15 m (< -5.9 in) for 2 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_DRUM_LVL_LO -->

Drum level reading is below the low alarm point.

**Probable causes**

- Feedwater not keeping up: feed pump lost or degraded, FRV not opening.
- A sudden steam-demand drop (shrink) on the Åström–Bell drum model, which recovers by itself.
- Drum level transmitter reading low while true level is normal.

**Actions**

1. Compare feed flow with steam flow. Normal steady state is feed = steam + pegging steam (chapter 01).
2. Check the running feed pump's lamp, current and NPSH margin, and the FRV position against its controller output.
3. If the level keeps falling and feed is short, start the standby feed pump (AOP-02).
4. If the reading disagrees with the flow balance, suspect the transmitter (AOP-04).

## DRUM_LVL_LOLO

<!-- BEGIN GENERATED: arp_DRUM_LVL_LOLO -->
**Window:** DRUM LEVEL / LOW LOW · **Condition:** `drum_level` < -0.3 m (< -11.8 in) for 1 s · **Latching:** yes · **Automatic action:** master fuel trip, turbine trip
<!-- END GENERATED: arp_DRUM_LVL_LOLO -->

Drum level reading is below the low-low trip point. The plant trips (MFT + turbine trip).

**Probable causes**

- Loss of feedwater not recovered in time.
- A drum level transmitter failing low (the trip acts on the sensed value).

**Actions**

1. Confirm MFT and turbine trip; follow AOP-08 (post-trip).
2. Read the first-out record to find the initiator.

## DRUM_LVL_HI

<!-- BEGIN GENERATED: arp_DRUM_LVL_HI -->
**Window:** DRUM LEVEL / HIGH · **Condition:** `drum_level` > 0.15 m (> 5.9 in) for 2 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_DRUM_LVL_HI -->

Drum level reading is above the high alarm point.

**Probable causes**

- Overfeeding: FRV stuck open or level loop in manual with too high a command.
- Swell after a steam-demand increase on the Åström–Bell drum.
- Loss of cold feed on the Åström–Bell drum (level rises first, then falls).
- Drum level transmitter reading high.

**Actions**

1. Check feed flow against steam flow and the FRV position against its controller output.
2. If a feed pump has just been lost, expect the level to turn and fall; prepare AOP-02.
3. If the FRV is not following its controller, take the level loop to manual (AOP-05).

## DRUM_LVL_HIHI

<!-- BEGIN GENERATED: arp_DRUM_LVL_HIHI -->
**Window:** DRUM LEVEL / HIGH HIGH · **Condition:** `drum_level` > 0.3 m (> 11.8 in) for 1 s · **Latching:** yes · **Automatic action:** turbine trip
<!-- END GENERATED: arp_DRUM_LVL_HIHI -->

Drum level reading is above the high-high trip point. The turbine trips.

**Probable causes**

- Uncontrolled overfeed.
- Level rise after loss of cold feed on the Åström–Bell drum.
- Transmitter failing high.

**Actions**

1. Confirm the turbine trip; follow AOP-08.
2. Read the first-out record.

## DRUM_P_HI

<!-- BEGIN GENERATED: arp_DRUM_P_HI -->
**Window:** DRUM PRESS / HIGH · **Condition:** `drum_pressure` > 8.4 MPa (> 1204 psig) for 2 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_DRUM_P_HI -->

Drum pressure is above the high alarm point.

**Probable causes**

- Steam demand fell faster than firing (load rejection, loss of pegging-steam demand).
- Loss of feedwater: feed is the boiler's heat sink, and losing it raises pressure.
- Drum pressure loop in manual with firing too high.

**Actions**

1. Check firing rate against its controller output and the pressure loop mode.
2. If feed has been lost, follow AOP-02. If pressure keeps rising, reduce firing (manual) before the safety valve lifts (AOP-07).

## SAFETY_VALVE

<!-- BEGIN GENERATED: arp_SAFETY_VALVE -->
**Window:** SAFETY VALVE / OPEN · **Condition:** `drum_pressure` > 8.6 MPa (> 1233 psig) for 0 s · **Latching:** no · **Automatic action:** safety valve lifts
<!-- END GENERATED: arp_SAFETY_VALVE -->

The drum safety valve has lifted.

**Probable causes**

- Pressure overshoot after loss of feed or a large load rejection with firing still high.

**Actions**

1. Follow AOP-07. Reduce firing; restore feedwater. The valve reseats by itself at its reseat pressure.

## DRUM_P_LO

<!-- BEGIN GENERATED: arp_DRUM_P_LO -->
**Window:** DRUM PRESS / LOW · **Condition:** `drum_pressure` < 7.2 MPa (< 1030 psig) for 5 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_DRUM_P_LO -->

Drum pressure is below the low alarm point.

**Probable causes**

- Firing not keeping up with steam demand (firing at maximum, degraded combustion).
- Pressure loop in manual with firing too low.
- A drum pressure transmitter reading low.

**Actions**

1. Check the firing rate: if it is at maximum, reduce load (shed non-vital or lower the load reference).
2. Compare drum pressure with steam-chest pressure and steam flow for consistency.

## FREQ_LO

<!-- BEGIN GENERATED: arp_FREQ_LO -->
**Window:** BUS FREQ / LOW · **Condition:** `frequency` < 59.5 Hz for 2 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_FREQ_LO -->

Bus frequency is below the low alarm point.

**Probable causes**

- Load increased with no load-reference trim.
- Turbine output reduced: worse condenser vacuum, throttle not opening, drum pressure low.

**Actions**

1. Raise the load reference (NOP-03).
2. If frequency keeps falling toward the load-shed point, shed the non-vital block (AOP-06).

## FREQ_HI

<!-- BEGIN GENERATED: arp_FREQ_HI -->
**Window:** BUS FREQ / HIGH · **Condition:** `frequency` > 60.5 Hz for 2 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_FREQ_HI -->

Bus frequency is above the high alarm point.

**Probable causes**

- Load dropped (for example after a load shed) with no trim.

**Actions**

1. Lower the load reference (NOP-03). Watch for overspeed (AOP-06).

## UF_SHED

<!-- BEGIN GENERATED: arp_UF_SHED -->
**Window:** UNDERFREQ / LOAD SHED · **Condition:** `frequency` < 58.8 Hz for 1 s · **Latching:** no · **Automatic action:** shed non-vital load
<!-- END GENERATED: arp_UF_SHED -->

Underfrequency: the non-vital load block has been shed automatically.

**Probable causes**

- Severe generation shortfall; frequency reached the shed point.

**Actions**

1. Expect frequency to rise sharply after the shed. Lower the load reference to avoid overspeed (AOP-06).
2. Find and correct the shortfall before reconnecting the non-vital block.

## UF_TRIP

<!-- BEGIN GENERATED: arp_UF_TRIP -->
**Window:** UNDERFREQ / TURB TRIP · **Condition:** `frequency` < 57 Hz for 2 s · **Latching:** yes · **Automatic action:** turbine trip
<!-- END GENERATED: arp_UF_TRIP -->

Underfrequency trip: the turbine has tripped.

**Probable causes**

- Frequency stayed below the underfrequency trip point after load shedding.

**Actions**

1. Follow AOP-08.

## OVERSPEED

<!-- BEGIN GENERATED: arp_OVERSPEED -->
**Window:** TURBINE / OVERSPEED · **Condition:** `frequency` > 66 Hz for 0 s · **Latching:** yes · **Automatic action:** turbine trip
<!-- END GENERATED: arp_OVERSPEED -->

Turbine overspeed trip.

**Probable causes**

- Large load rejection (including an underfrequency load shed) faster than the throttle could close.

**Actions**

1. Follow AOP-08. If the throttle was slow to close, suspect its actuator.

## FP1_SUCTION

<!-- BEGIN GENERATED: arp_FP1_SUCTION -->
**Window:** FP-1 SUCTION / LOW NPSH · **Condition:** `fp1_npsh_margin` < 0.5 m (< 1.6 ft) for 5 s · **Latching:** yes · **Automatic action:** trip FP-1
<!-- END GENERATED: arp_FP1_SUCTION -->

FP-1 suction margin (NPSH) low: FP-1 has tripped.

**Probable causes**

- DA level low: condensate flow lost (condensate pump trip) or the DA LCV not opening.
- Excessive FP-1 flow.

**Actions**

1. Start FP-2 at once if available (AOP-02); restore condensate flow (AOP-01).

## FP2_SUCTION

<!-- BEGIN GENERATED: arp_FP2_SUCTION -->
**Window:** FP-2 SUCTION / LOW NPSH · **Condition:** `fp2_npsh_margin` < 0.5 m (< 1.6 ft) for 5 s · **Latching:** yes · **Automatic action:** trip FP-2
<!-- END GENERATED: arp_FP2_SUCTION -->

FP-2 suction margin (NPSH) low: FP-2 has tripped.

**Probable causes**

- As for FP1_SUCTION.

**Actions**

1. Start FP-1 at once if available (AOP-02); restore condensate flow (AOP-01).

## CP1_SUCTION

<!-- BEGIN GENERATED: arp_CP1_SUCTION -->
**Window:** CP-1 SUCTION / LOW NPSH · **Condition:** `cp1_npsh_margin` < 0.25 m (< 0.8 ft) for 5 s · **Latching:** yes · **Automatic action:** trip CP-1
<!-- END GENERATED: arp_CP1_SUCTION -->

CP-1 suction margin (NPSH) low: CP-1 has tripped.

**Probable causes**

- Hotwell level low: water leaving the cycle with makeup not keeping up or not available.
- Excessive CP-1 flow.

**Actions**

1. Start CP-2 if its own margin allows (AOP-01); restore hotwell level (AOP-09).

## CP2_SUCTION

<!-- BEGIN GENERATED: arp_CP2_SUCTION -->
**Window:** CP-2 SUCTION / LOW NPSH · **Condition:** `cp2_npsh_margin` < 0.25 m (< 0.8 ft) for 5 s · **Latching:** yes · **Automatic action:** trip CP-2
<!-- END GENERATED: arp_CP2_SUCTION -->

CP-2 suction margin (NPSH) low: CP-2 has tripped.

**Probable causes**

- As for CP1_SUCTION.

**Actions**

1. Start CP-1 if its own margin allows (AOP-01); restore hotwell level (AOP-09).

## HOTWELL_LO

<!-- BEGIN GENERATED: arp_HOTWELL_LO -->
**Window:** HOTWELL LVL / LOW · **Condition:** `hotwell_level` < -0.5 m (< -19.7 in) for 5 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_HOTWELL_LO -->

Hotwell level is low.

**Probable causes**

- Water leaving the cycle faster than makeup replaces it, or the makeup valve not opening.
- Condensate pumped out faster than the turbine exhaust condenses (DA LCV wide open).

**Actions**

1. Check makeup flow and the makeup valve against its controller output (AOP-09). If the cycle is losing water faster than makeup, the condensate pumps will lose suction: prepare to reduce load.

## HOTWELL_HI

<!-- BEGIN GENERATED: arp_HOTWELL_HI -->
**Window:** HOTWELL LVL / HIGH · **Condition:** `hotwell_level` > 0.5 m (> 19.7 in) for 5 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_HOTWELL_HI -->

Hotwell level is high.

**Probable causes**

- Condensate not being removed: condensate pump tripped, or DA LCV not opening.
- Inventory moved out of the drum into the hotwell.

**Actions**

1. Check the condensate pump lamps and current and the DA LCV position against its controller output; follow AOP-01 if condensate flow has been lost.

## DA_LO

<!-- BEGIN GENERATED: arp_DA_LO -->
**Window:** DA LEVEL / LOW · **Condition:** `da_level` < -0.5 m (< -19.7 in) for 5 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_DA_LO -->

Deaerator level is low.

**Probable causes**

- Condensate flow lost or reduced (condensate pump trip, DA LCV not opening).
- Feed flow above condensate flow for a long period.

**Actions**

1. The DA is the feed pumps' suction supply: restoring condensate flow is urgent (AOP-01).

## DA_HI

<!-- BEGIN GENERATED: arp_DA_HI -->
**Window:** DA LEVEL / HIGH · **Condition:** `da_level` > 0.5 m (> 19.7 in) for 5 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_DA_HI -->

Deaerator level is high.

**Probable causes**

- DA LCV stuck open or DA level loop in manual with too high a command.
- Feed flow reduced (feed pump trip).

**Actions**

1. Check the DA LCV against its controller output; take the DA level loop to manual if necessary (AOP-05).

## COND_P_HI

<!-- BEGIN GENERATED: arp_COND_P_HI -->
**Window:** COND PRESS / HIGH · **Condition:** `cond_pressure` > 12 kPa (< 26.4 inHg vac) for 5 s · **Latching:** no · **Automatic action:** alarm only
<!-- END GENERATED: arp_COND_P_HI -->

Condenser pressure is high (vacuum low).

**Probable causes**

- Air in-leakage.
- Condenser heat-transfer degradation (fouling): the rise grows with load.
- A condenser pressure transmitter reading high.

**Actions**

1. Follow AOP-03. Reducing load lowers the load-dependent part of condenser pressure.

## COND_P_HIHI

<!-- BEGIN GENERATED: arp_COND_P_HIHI -->
**Window:** COND PRESS / HIGH HIGH · **Condition:** `cond_pressure` > 18 kPa (< 24.6 inHg vac) for 5 s · **Latching:** yes · **Automatic action:** turbine trip
<!-- END GENERATED: arp_COND_P_HIHI -->

Condenser pressure high-high (vacuum very low): the turbine has tripped.

**Probable causes**

- Unchecked loss of vacuum.

**Actions**

1. Follow AOP-08.
