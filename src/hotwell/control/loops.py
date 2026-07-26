"""The four plant control loops (plan section 6), all acting on SENSED values.

- Governor: pure droop (proportional only) — islanded frequency offset under
  load change is expected and correct. x_cmd = x_rated*(load_ref/P_rated -
  (1/R)*(f - f0)/f0); x_rated scales the per-unit power command onto the valve
  so that load_ref = P_rated at f = f0 gives exactly rated flow (throttle k_t
  is calibrated at x_rated).
- Drum level -> feed valve command. Single-element PI by default; the M4
  three-element option (behind config flag) adds steam-flow feedforward with
  a feed-flow trim loop: flow demand = sensed steam flow + level-trim PI
  [kg/s], and an inner flow PI drives the valve to match sensed feed flow.
- Drum pressure -> firing command.
- DA level -> DA level-control valve position (direct, no actuator lag).
"""
from __future__ import annotations

from dataclasses import dataclass

from hotwell.control.pid import PI, PIParams


@dataclass(frozen=True)
class GovernorParams:
    droop: float     # R [-], e.g. 0.05
    p_rated: float   # rated electrical power [W]
    f0: float        # rated frequency [Hz]
    x_rated: float   # throttle position at rated command [-]


@dataclass(frozen=True)
class Commands:
    """Actuator commands, frozen during the RK4 stages of one step."""

    fw_cmd: float       # feed reg valve command [-]
    throttle_cmd: float  # throttle command [-]
    firing_cmd: float   # firing command [-]
    lcv_x: float        # DA level-control valve position [-]


class ControlSystem:
    """Owns the loops and produces Commands from the previous observation."""

    def __init__(self, gov: GovernorParams,
                 level_pi: PIParams, level_sp: float,
                 pressure_pi: PIParams, pressure_sp: float,
                 da_pi: PIParams, da_sp: float,
                 three_element: bool = False,
                 te_trim: PIParams | None = None,
                 te_flow: PIParams | None = None) -> None:
        self.gov = gov
        self.load_ref = 0.0  # operator load reference [W]
        self.drum_level = PI(level_pi, level_sp)
        self.drum_pressure = PI(pressure_pi, pressure_sp)
        self.da_level = PI(da_pi, da_sp)
        self.governor_manual: float | None = None  # manual throttle cmd, None = auto
        self.three_element = three_element
        if three_element:
            assert te_trim is not None and te_flow is not None
            self.fw_trim = PI(te_trim, level_sp)   # level [m] -> flow trim [kg/s]
            self.fw_flow = PI(te_flow, 0.0)        # feed flow [kg/s] -> valve [-]

    def loop(self, name: str) -> PI:
        return {"drum_level": self.drum_level,
                "drum_pressure": self.drum_pressure,
                "da_level": self.da_level}[name]

    def governor_cmd(self, f_sensed: float) -> float:
        """Droop law -> throttle command [-] from sensed frequency [Hz]."""
        if self.governor_manual is not None:
            x = self.governor_manual
        else:
            g = self.gov
            x = g.x_rated * (self.load_ref / g.p_rated
                             - (1.0 / g.droop) * (f_sensed - g.f0) / g.f0)
        return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

    def _fw_cmd(self, sensed: dict[str, float], dt: float) -> float:
        if not self.three_element:
            return self.drum_level.update(sensed["drum_level"], dt)
        # three-element: drum_level.mode still carries the loop's auto/manual
        # switch; its manual_cmd drives the valve directly in manual.
        mode = self.drum_level.mode
        self.fw_trim.mode = mode
        self.fw_flow.mode = mode
        self.fw_flow.manual_cmd = self.drum_level.manual_cmd
        trim = self.fw_trim.update(sensed["drum_level"], dt)
        self.fw_flow.sp = sensed["steam_flow"] + trim
        u = self.fw_flow.update(sensed["feed_flow"], dt)
        self.drum_level.output = u  # display/telemetry consistency
        return u

    def update(self, sensed: dict[str, float], dt: float) -> Commands:
        """One 20 Hz controller pass using the previous step's sensed values."""
        return Commands(
            fw_cmd=self._fw_cmd(sensed, dt),
            throttle_cmd=self.governor_cmd(sensed["frequency"]),
            firing_cmd=self.drum_pressure.update(sensed["drum_pressure"], dt),
            lcv_x=self.da_level.update(sensed["da_level"], dt),
        )
