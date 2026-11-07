"""0.4.0 M4: 24-h quiet-day acceptance run (slow; `pytest -m slow -s`).

Pass criteria from the plan: no protective trips, no rejected actions, mass
audit drift < 0.1 %. Alarms are printed, not failed on (they get explained in
HANDOFF). Until M6 the operator's frequency trims are a fixed load-reference
schedule (scripts/quiet_day.py docstring).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "quiet_day", Path(__file__).resolve().parents[1] / "scripts" / "quiet_day.py")
quiet_day = importlib.util.module_from_spec(_spec)
sys.modules["quiet_day"] = quiet_day  # @dataclass resolves annotations via sys.modules
_spec.loader.exec_module(quiet_day)


@pytest.mark.slow
@pytest.mark.parametrize("fidelity", sorted(quiet_day.FIDELITIES))
def test_quiet_day(fidelity):
    r = quiet_day.run_quiet_day(fidelity, seed=42, until_h=24.0, progress=False)
    quiet_day.print_result(r)
    assert r.t_end == pytest.approx(86400.0, abs=0.1)
    assert not any(r.trips.values()), r.trips
    assert not r.first_out
    assert not r.rejected
    assert abs(r.mass_drift_frac) < 1e-3
    # M5b G6: makeup never opens in normal operation (no inventory ratchet).
    # Gate on the makeup VALVE command (truth-side, exact), since the sensed
    # makeup_flow carries noise around zero.
    assert r.makeup_max_cmd == 0.0, r.makeup_max_cmd


_rd_spec = importlib.util.spec_from_file_location(
    "level_mode_ringdown",
    Path(__file__).resolve().parents[1] / "scripts" / "level_mode_ringdown.py")
level_mode_ringdown = importlib.util.module_from_spec(_rd_spec)
sys.modules["level_mode_ringdown"] = level_mode_ringdown
_rd_spec.loader.exec_module(level_mode_ringdown)


@pytest.mark.slow
def test_ab_3e_slow_level_mode_is_damped():
    """M4b regression gate. History: with trim kp 15 / ki 0.15 (Ti = 100 s) the
    AB + 3E ~1890 s level mode had negative damping (zeta ~ -0.02, pre-existing
    in 0.3.0; it was a strict xfail here). Reduced model: unstable iff
    Ti = kp/ki < kappa*rhoA ~ 116 s. Retuned to kp 30 / ki 0.075 (Ti 400 s).
    Gate: residual oscillation in the last 2 h < 10 % of the first peak, and a
    positive damping estimate."""
    r = level_mode_ringdown.ringdown("astrom_bell", None, hours=6.0)
    print(f"\nfirst extrema {[(round(t), round(x * 1e3, 1)) for t, x in r['extrema'][:4]]}; "
          f"zeta (half cycle) {r['zeta_half_cycle']}; late/first {r['late_over_first_peak']:.3f}; "
          f"load-step peak {r['peak_abs_mm']:+.1f} mm")
    assert r["late_over_first_peak"] < 0.10
    assert r["zeta_half_cycle"] is not None and r["zeta_half_cycle"] > 0.2


@pytest.mark.slow
def test_two_state_3e_slow_level_mode_is_damped():
    """Control case: same loop on the two-state drum (kappa = 0) is always
    damped, under the old and the new trim tuning."""
    r = level_mode_ringdown.ringdown("two_state", None, hours=6.0)
    print(f"\nfirst extrema {[(round(t), round(x * 1e3, 1)) for t, x in r['extrema'][:4]]}; "
          f"zeta (half cycle) {r['zeta_half_cycle']}; late/first {r['late_over_first_peak']:.3f}")
    assert r["late_over_first_peak"] < 0.10
