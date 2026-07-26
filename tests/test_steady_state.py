"""T2/T3/T4 — steady-state initialization, 600 s hold, mass & energy closure."""
import numpy as np
import pytest

from hotwell.simulator import Simulator


@pytest.fixture(scope="module")
def sim600():
    """Initialize at 60 MW and run 600 s under automatic control."""
    sim = Simulator(seed=0)
    sim.initialize_steady_state(60.0)
    y0 = sim.y.copy()
    resid0 = sim.steady_state_residual_norm()
    sim.run(600.0)
    return sim, y0, resid0


def test_t2_initial_residual(sim600):
    _, _, resid0 = sim600
    print(f"scaled |ydot|_max at init: {resid0:.3e} 1/s")
    assert resid0 < 1e-7


def test_t2_hold_600s(sim600):
    sim, y0, _ = sim600
    spans = sim.plant.registry.spans()
    names = sim.plant.registry.names()
    drift = np.abs(sim.y - y0) / spans
    for n, d0, d1, dr in zip(names, y0, sim.y, drift, strict=True):
        print(f"{n:14s} {d0:14.6g} -> {d1:14.6g}   drift {dr * 100:8.4f}% of span")
    assert sim.t >= 599.9
    assert not sim.disc.plant_dead
    assert float(np.max(drift)) < 0.01


def test_t3_mass_audit(sim600):
    sim, _, _ = sim600
    rep = sim.audit()
    print(f"mass drift over 600 s: {rep.mass_drift_frac * 100:.6f}% "
          f"({rep.mass_drift_frac_per_hour * 100:.6f}%/h), "
          f"inventory {rep.mass_total / 1e3:.2f} t, relief {rep.mass_relief_integrated:.3f} kg")
    assert abs(rep.mass_drift_frac) < 0.005


def test_t4_energy_audit(sim600):
    sim, _, _ = sim600
    rep = sim.audit()
    print(f"energy residual: {rep.energy_residual / 1e6:.4f} MW "
          f"({rep.energy_residual_frac * 100:.4f}% of firing)")
    assert abs(rep.energy_residual_frac) < 0.02
