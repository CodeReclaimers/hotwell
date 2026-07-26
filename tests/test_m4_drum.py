"""M4 — AstromBellDrum steady behavior + three-element feedwater option."""
import numpy as np
import pytest

from hotwell import data
from hotwell.plant import load_config
from hotwell.simulator import Simulator


@pytest.fixture(scope="module")
def ab_sim():
    cfg = load_config()
    cfg["drum"]["model"] = "astrom_bell"
    sim = Simulator(cfg, seed=0)
    sim.initialize_steady_state(60.0)
    return sim


def test_ab_steady_state_and_hold(ab_sim):
    sim = ab_sim
    resid = sim.steady_state_residual_norm()
    y0 = sim.y.copy()
    sim.run(300.0)
    spans = sim.plant.registry.spans()
    drift = np.abs(sim.y - y0) / spans
    for n, dr in zip(sim.plant.registry.names(), drift, strict=True):
        if dr > 1e-5:
            print(f"{n:16s} drift {dr * 100:.4f}% of span")
    print(f"AB init residual {resid:.2e} 1/s; max 300 s drift "
          f"{float(np.max(drift)) * 100:.4f}% of span")
    assert resid < 1e-7
    assert float(np.max(drift)) < 0.01
    assert sim.last_obs.alarms == []


def test_ab_mass_energy_audit(ab_sim):
    rep = ab_sim.audit()
    print(f"AB audit: mass drift {rep.mass_drift_frac * 100:.6f}% of "
          f"{rep.mass_total / 1e3:.1f} t; energy {rep.energy_residual_frac * 100:.4f}%")
    assert abs(rep.mass_drift_frac) < 0.005
    assert abs(rep.energy_residual_frac) < 0.02


def test_ab_design_point_documented(ab_sim):
    """The derived design values HANDOFF documents must match the code."""
    d = ab_sim.plant.drum
    print(f"alpha_r nominal {d.ar_nom:.4f}, V_sd0 {d.vsd0:.2f} m3, "
          f"V_wt nominal {d.vwt_nom:.2f} m3, level ref {d.ref_below:.2f} m3")
    assert 0.08 < d.ar_nom < 0.14          # paper's high-load quality range
    assert d.vsd0 > d.vsd_nom              # subcooled feed condenses drum steam


def _load_step_peak(three_element: bool) -> tuple[float, float]:
    """(peak |level| [m], settled |level| [m]) for the +6 MW load step."""
    cfg = load_config()
    cfg["control"]["drum_level"]["three_element"] = three_element
    from hotwell.scenario import load_scenario
    sim = Simulator(cfg, scenario=load_scenario(data.builtin_scenarios()["load_step"]))
    sim.initialize_steady_state(sim.scenario.load_mw)
    sim.run(300.0)
    peak = 0.0
    while sim.t < 600.0:
        sim.step()
        peak = max(peak, abs(sim.last_aux.drum_level))
    assert sim.last_obs.alarms == []
    return peak, abs(sim.last_aux.drum_level)


def test_three_element_feedwater():
    peak_1e, settle_1e = _load_step_peak(False)
    peak_3e, settle_3e = _load_step_peak(True)
    print(f"load-step drum level: single-element peak {peak_1e * 1e3:.1f} mm "
          f"(settle {settle_1e * 1e3:.1f}), three-element peak {peak_3e * 1e3:.1f} mm "
          f"(settle {settle_3e * 1e3:.1f})")
    # feedforward must not be worse than single-element, and must stay stable
    assert peak_3e <= peak_1e + 0.002
    assert settle_3e < 0.02
