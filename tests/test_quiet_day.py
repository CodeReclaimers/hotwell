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


_rd_spec = importlib.util.spec_from_file_location(
    "level_mode_ringdown",
    Path(__file__).resolve().parents[1] / "scripts" / "level_mode_ringdown.py")
level_mode_ringdown = importlib.util.module_from_spec(_rd_spec)
sys.modules["level_mode_ringdown"] = level_mode_ringdown
_rd_spec.loader.exec_module(level_mode_ringdown)


@pytest.mark.slow
@pytest.mark.xfail(strict=True, reason=(
    "KNOWN DEFECT (found by the M4 quiet-day run, 2026-11-07; pre-existing in "
    "0.3.0): AB drum + three-element feedwater has a ~1890 s drum-level mode "
    "with NEGATIVE damping (zeta ~ -0.02). See HANDOFF 0.4.0 'known issue'. "
    "strict=True: once the loop is fixed this XPASSes and fails the run, so "
    "the marker must be removed deliberately."))
def test_ab_3e_slow_level_mode_is_damped():
    r = level_mode_ringdown.ringdown("astrom_bell", None, hours=6.0)
    print(f"\nperiods {[round(p) for p in r['periods'][:6]]} s; "
          f"zeta {[round(z, 3) for z in r['zetas'][:6]]}")
    assert r["zetas"][1:6] and all(z > 0.0 for z in r["zetas"][1:6])


@pytest.mark.slow
def test_two_state_3e_slow_level_mode_is_damped():
    """Control case for the xfail above: same loop, two-state drum: damped
    (zeta ~ +0.09..0.14), so the inverse response is what tips AB unstable."""
    r = level_mode_ringdown.ringdown("two_state", None, hours=6.0)
    print(f"\nperiods {[round(p) for p in r['periods'][:5]]} s; "
          f"zeta {[round(z, 3) for z in r['zetas'][:5]]}")
    assert all(z > 0.0 for z in r["zetas"][:5])
