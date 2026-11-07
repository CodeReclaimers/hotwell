"""SI -> US customary display conversions (0.4.0, plan M7).

`hotwell` is SI throughout; this module is presentation only, used by the
manual generator (scripts/gen_manual.py) and available to any consumer. The
constants and per-instrument choices are copied EXACTLY from
hotwell-panel/src/hotwell_panel/displayunits.py, so the manual and the
1970s board print the same numbers. Until the panel switches to this module
(a separate panel task, with a parity test there) there are two copies.

Every conversion is affine: display = si * scale + offset. Condenser pressure
is shown as VACUUM (inHg vac, higher is better), so its scale is negative.
Pump currents, which the panel shows as % of rated amps, are left in amperes
here: the manual quotes amps.
"""
from __future__ import annotations

from dataclasses import dataclass

PA_PER_PSI = 6894.757293168361
PA_PER_INHG = 3386.388640341
ATM_PA = 101325.0
M_PER_IN = 0.0254
M_PER_FT = 0.3048
KG_PER_LB = 0.45359237


@dataclass(frozen=True)
class Customary:
    unit: str
    scale: float
    offset: float
    decimals: int

    def convert(self, si: float) -> float:
        return si * self.scale + self.offset

    def fmt(self, si: float) -> str:
        return f"{self.convert(si):.{self.decimals}f} {self.unit}"


PSIG = Customary("psig", 1.0 / PA_PER_PSI, -ATM_PA / PA_PER_PSI, 0)
PSIG_1 = Customary("psig", 1.0 / PA_PER_PSI, -ATM_PA / PA_PER_PSI, 1)
INHG_VAC = Customary("inHg vac", -1.0 / PA_PER_INHG, ATM_PA / PA_PER_INHG, 1)
INCHES = Customary("in", 1.0 / M_PER_IN, 0.0, 1)
FEET = Customary("ft", 1.0 / M_PER_FT, 0.0, 1)
KLB_HR = Customary("klb/hr", 3600.0 / KG_PER_LB / 1000.0, 0.0, 0)
MW = Customary("MW", 1e-6, 0.0, 1)
HZ = Customary("Hz", 1.0, 0.0, 2)
PERCENT = Customary("%", 100.0, 0.0, 0)
AMPS = Customary("A", 1.0, 0.0, 0)
DEGF_FROM_K = Customary("°F", 9.0 / 5.0, -273.15 * 9.0 / 5.0 + 32.0, 0)

#: instrument name -> customary display (the panel's choices).
INSTRUMENT_UNITS: dict[str, Customary] = {
    "drum_pressure": PSIG, "chest_pressure": PSIG, "da_pressure": PSIG_1,
    "cond_pressure": INHG_VAC,
    "drum_level": INCHES, "hotwell_level": INCHES, "da_level": INCHES,
    "steam_flow": KLB_HR, "feed_flow": KLB_HR, "condensate_flow": KLB_HR,
    "frequency": HZ, "mw_out": MW,
    "fw_valve_pos": PERCENT, "throttle_pos": PERCENT, "firing_rate": PERCENT,
    "da_lcv_pos": PERCENT,
    "cp1_current": AMPS, "cp2_current": AMPS, "fp1_current": AMPS, "fp2_current": AMPS,
    "fp1_npsh_margin": FEET, "fp2_npsh_margin": FEET,
    # 0.4.0 M5b instruments (the panel's choices for the same quantity kinds)
    "makeup_flow": KLB_HR, "makeup_valve_pos": PERCENT,
    "cp1_npsh_margin": FEET, "cp2_npsh_margin": FEET,
}


def fmt(name: str, si: float) -> str:
    """Customary rendering of an SI value of instrument `name`."""
    return INSTRUMENT_UNITS[name].fmt(si)
