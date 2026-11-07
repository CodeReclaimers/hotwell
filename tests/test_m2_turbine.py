"""0.4.0 M2: backpressure- and inlet-pressure-dependent turbine work, plus
the COND_P_HIHI low-vacuum trip."""
import numpy as np
import pytest

from hotwell import steam_properties as sp
from hotwell.components.turbine import isentropic_drop
from hotwell.plant import load_config
from hotwell.scenario import Scenario, ScenarioEvent
from hotwell.simulator import Simulator


@pytest.fixture(scope="module")
def rated():
    sim = Simulator(load_config(), seed=0)
    sim.initialize_steady_state(60.0)
    return sim


def test_design_point_work_is_exact(rated):
    """eta_t is derived so that w == w_design at the design state, which keeps
    k_t, the droop calibration and the 60 MW anchor exact.

    Two checks. (1) At the calibration point itself (8 MPa; the condenser
    model's pressure at rated exhaust flow), exact to 1e-9 (plan M2).
    (2) At the SOLVED steady state, which isn't exactly the design flow:
    the station-service fixed point in initialize_steady_state stops within
    1 kW (simulator.py, `< 1e3`), and 0.3.0 itself sits +1.02e-4 kg/s /
    +79 W off design (measured 2026-11-07 on pristine 9464eb2). 1 kW/60 MW
    = 1.7e-5 in flow -> <= 0.025 Pa of p_cond -> |dw/w| <= 0.025 * 11 /
    780e3 = 3.6e-7, so that check uses 1e-6."""
    tb, aux = rated.plant.turbine, rated.last_aux
    tp = tb.tp
    pd0 = rated.cfg["design"]["p_drum"]
    pc0 = rated.plant.condenser.p_cond(tp.k_t * tp.x_rated * pd0, 0.0)
    w_cal = tb.specific_work(pd0, pc0)
    w = tb.specific_work(aux.p_drum, aux.p_cond)
    print(f"\neta_t {tb.eta_t:.6f}; calibration point ({pd0:.0f} Pa, {pc0:.4f} Pa): "
          f"w - 780 kJ/kg = {w_cal - 780e3:.3e} J/kg"
          f"\nsolved state (p_drum {aux.p_drum:.4f} Pa, p_cond {aux.p_cond:.4f} Pa): "
          f"w - 780 kJ/kg = {w - 780e3:.3e} J/kg (rel {(w - 780e3) / 780e3:.2e}); "
          f"p_mech {aux.p_mech / 1e6:.6f} MW")
    assert w_cal == pytest.approx(780.0e3, rel=1e-9)
    assert w == pytest.approx(780.0e3, rel=1e-6)
    assert aux.p_mech == pytest.approx(60.0e6, rel=1e-5)
    assert 0.79 < tb.eta_t < 0.81  # the 0.3.0 config comment said "eta 0.80"


@pytest.mark.parametrize("p_d", [7.0e6, 8.0e6, 9.0e6])
@pytest.mark.parametrize("p_c", [5.5e3, 7.0e3, 12.0e3, 18.0e3])
def test_backpressure_derivative_matches_thermodynamics(rated, p_d, p_c):
    """At constant entropy dh = v dp, so dw/dp_cond = -eta_t * v_2s with
    v_2s = v_f + x_2s * v_fg. v_fg comes from Clapeyron,
    v_fg = h_fg / (T dpsat/dT), using the psat(T) fit: an identity the turbine
    code never evaluates, so the finite difference is checked against
    independent thermodynamics rather than against itself."""
    tb = rated.plant.turbine
    d = 5.0
    fd = (tb.specific_work(p_d, p_c + d) - tb.specific_work(p_d, p_c - d)) / (2 * d)
    t_c = sp.tsat_lowp(p_c)
    h_fg = sp.hg_t(t_c) - sp.hf_t(t_c)
    x_2s = (sp.s_g(p_d) - sp.sf_t(t_c)) / (h_fg / t_c)
    dt = 0.01
    dpsat_dt = (sp.psat(t_c + dt) - sp.psat(t_c - dt)) / (2 * dt)
    v_fg = h_fg / (t_c * dpsat_dt)
    analytic = -tb.eta_t * (1.0 / sp.rho_f_t(t_c) + x_2s * v_fg)
    rel = abs(fd - analytic) / abs(analytic)
    print(f"\np_d {p_d / 1e6:.0f} MPa p_c {p_c / 1e3:5.1f} kPa: x_2s {x_2s:.4f} "
          f"dw/dp_c FD {fd:8.4f} analytic {analytic:8.4f} J/kg/Pa (rel {rel:.2e})")
    assert fd < 0.0
    assert rel < 0.01


def test_work_rises_with_drum_pressure_and_falls_with_backpressure(rated):
    tb = rated.plant.turbine
    pcs = np.linspace(5.5e3, 20.0e3, 30)
    pds = np.linspace(6.0e6, 10.0e6, 30)
    w_c = [tb.specific_work(8.0e6, pc) for pc in pcs]
    w_d = [tb.specific_work(pd, 7.0e3) for pd in pds]
    print(f"\nw(8 MPa, p_c) {w_c[0] / 1e3:.1f} -> {w_c[-1] / 1e3:.1f} kJ/kg over "
          f"5.5-20 kPa; w(p_d, 7 kPa) {w_d[0] / 1e3:.1f} -> {w_d[-1] / 1e3:.1f} "
          f"kJ/kg over 6-10 MPa")
    assert np.all(np.diff(w_c) < 0)
    assert np.all(np.diff(w_d) > 0)


def test_isentropic_drop_design_value_against_hand_steam_tables():
    """Hand-check anchor (plan M2): s_g(8 MPa) 5.743, 7 kPa -> x_2s ~ 0.672,
    h_2s ~ 1782 kJ/kg, dh_s ~ 976 kJ/kg."""
    dh = isentropic_drop(8.0e6, 7.0e3)
    print(f"\nisentropic drop 8 MPa -> 7 kPa: {dh / 1e3:.2f} kJ/kg")
    assert dh == pytest.approx(976.0e3, rel=0.005)


def test_air_ingress_step_settles_where_droop_predicts():
    """+5 kPa air-ingress step at rated, governor load reference held at 60 MW.

    Islanded: lost specific work pulls frequency down until the droop governor
    opens the throttle enough to rebalance. Steady state, with the drum
    pressure restored by its loop (p_d = design), delta = df/f0, and
    eps = 1 - w1/w0 evaluated at the final measured (p_drum, p_cond):
        P_m = (1 - eps) P_r (1 - delta/R)                 (droop, D6)
        P_e = P_blk (1 + k_pf delta) + P_ss1
    =>  delta = ((1 - eps) P_r - P_blk - P_ss1) / ((1 - eps) P_r / R + P_blk k_pf)
    The measured values are means over the last 60 s; the governor dithers on
    the 0.01 Hz frequency quantization (a known 0.3.0 rough edge)."""
    sc = Scenario(name="air_step", seed=0, load_mw=60.0, mode="islanded",
                  events=(ScenarioEvent(10.0, "set_air_ingress", {"value": 5000.0}),),
                  max_t=900.0)
    sim = Simulator(load_config(), scenario=sc)
    sim.initialize_steady_state(60.0)
    tb, loads = sim.plant.turbine, sim.plant.loads
    p_r = sim.cfg["design"]["p_rated"]
    r = sim.cfg["control"]["governor"]["droop"]
    p_blk = loads.vital.p0 + loads.nonvital.p0
    k_pf = loads.vital.k_pf
    f0 = sim.plant.turbine.rp.f0
    w0 = tb.specific_work(sim.last_aux.p_drum, sim.last_aux.p_cond)
    samples = []
    while sim.t < sc.max_t - 0.5 * sim.dt:
        sim.step()
        if sim.t > sc.max_t - 60.0:
            a = sim.last_aux
            omega = sim.y[tb.i_omega]
            samples.append((omega / (2 * np.pi), a.p_elec, a.p_station_service,
                            a.p_drum, a.p_cond))
    f, pe, pss, pd, pc = (float(np.mean(c)) for c in zip(*samples, strict=True))
    eps = 1.0 - tb.specific_work(pd, pc) / w0
    delta = ((1 - eps) * p_r - p_blk - pss) / ((1 - eps) * p_r / r + p_blk * k_pf)
    df_pred, df_meas = delta * f0, f - f0
    dpe_pred = p_blk * k_pf * delta + (pss - (p_r - p_blk))
    dpe_meas = pe - p_r
    print(f"\nfinal p_cond {pc / 1e3:.3f} kPa, p_drum {pd / 1e6:.4f} MPa, eps {eps:.4%}"
          f"\n  df   predicted {df_pred:+.4f} Hz   measured {df_meas:+.4f} Hz"
          f"\n  dP_e predicted {dpe_pred / 1e6:+.4f} MW  measured {dpe_meas / 1e6:+.4f} MW"
          f"\n  alarms {sim.last_obs.alarms}; rejected {sim.rejected}")
    assert pd == pytest.approx(8.0e6, rel=2e-3)
    assert df_meas == pytest.approx(df_pred, rel=0.03)
    assert dpe_meas == pytest.approx(dpe_pred, rel=0.05)
    assert dpe_meas < 0.0  # vacuum loss now costs output (gap 4 closed)
    rep = sim.audit()
    print(f"  audit: mass drift {rep.mass_drift_frac:.2e}, "
          f"energy residual {rep.energy_residual_frac:.2e} of firing")
    assert abs(rep.energy_residual_frac) < 1e-3


def test_air_ingress_ramp_trips_turbine_on_cond_p_hihi():
    """Air ingress ramped at 100 Pa/s from t = 10 s: COND_P_HI (12 kPa)
    alarms first, then COND_P_HIHI (18 kPa, 5 s) trips the turbine and is
    the first out. The trip setpoint sits inside the 0-20 kPa instrument
    range, so it is observable."""
    events = tuple(ScenarioEvent(10.0 + i, "set_air_ingress", {"value": 100.0 * (i + 1)})
                   for i in range(200))
    sc = Scenario(name="air_ramp", seed=0, load_mw=60.0, mode="islanded",
                  events=events, max_t=300.0)
    sim = Simulator(load_config(), scenario=sc)
    sim.initialize_steady_state(60.0)
    seen: dict[str, float] = {}
    while sim.t < sc.max_t and not sim.disc.turbine_trip:
        obs = sim.step()
        for aid, _ in obs.alarms:
            seen.setdefault(aid, round(sim.t, 2))
    print(f"\nfirst activations {seen}\nfirst_out "
          f"{[(round(t, 2), c) for t, c in sim.engine.first_out]}\n"
          f"turbine_trip {sim.disc.turbine_trip} at t={sim.t:.2f}, sensed "
          f"cond_pressure {sim.last_obs.values['cond_pressure']:.0f} Pa")
    assert sim.disc.turbine_trip
    assert sim.engine.first_out[0][1] == "COND_P_HIHI"
    assert seen["COND_P_HI"] < seen["COND_P_HIHI"]
    assert sim.last_obs.values["cond_pressure"] < 20.0e3
