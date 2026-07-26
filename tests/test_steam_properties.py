"""T1 — steam property anchor checks (plan section 5.1) plus fit self-consistency."""
import math

from hotwell import steam_properties as sp

T0_K = 273.15


def test_anchor_tsat_8mpa():
    t_c = sp.tsat(8.0e6) - T0_K
    print(f"Tsat(8 MPa) = {t_c:.2f} degC (anchor 295 +/- 1)")
    assert abs(t_c - 295.0) <= 1.0


def test_anchor_tsat_da_pressure():
    t_c = sp.tsat_lowp(0.15e6) - T0_K
    print(f"Tsat(0.15 MPa) = {t_c:.2f} degC (anchor 111.4 +/- 0.5)")
    assert abs(t_c - 111.4) <= 0.5


def test_anchor_hg_8mpa():
    hg = sp.h_g(8.0e6) / 1e3
    print(f"h_g(8 MPa) = {hg:.1f} kJ/kg (anchor 2758 +/- 15)")
    assert abs(hg - 2758.0) <= 15.0


def test_psat_roundtrip():
    """psat and tsat_lowp must be mutual inverses across the low range."""
    worst = 0.0
    for t_c in (35.0, 50.0, 75.0, 100.0, 111.4, 125.0, 145.0):
        t = t_c + T0_K
        back = sp.tsat_lowp(sp.psat(t))
        worst = max(worst, abs(back - t))
    print(f"psat/tsat_lowp roundtrip worst |dT| = {worst * 1e3:.2f} mK")
    assert worst < 0.15  # K


def test_condenser_point():
    """7 kPa condenser: Tsat approx 39 degC, h_f approx 163 kJ/kg."""
    t = sp.tsat_lowp(7.0e3)
    hf = sp.hf_t(t) / 1e3
    print(f"Tsat(7 kPa) = {t - T0_K:.2f} degC, h_f = {hf:.1f} kJ/kg")
    assert abs((t - T0_K) - 39.0) <= 0.8
    assert abs(hf - 163.4) <= 2.0


def test_two_phase_ordering():
    """Physical sanity across the drum range."""
    for p_mpa in (3.0, 5.0, 8.0, 11.0, 12.0):
        p = p_mpa * 1e6
        assert sp.v_g(p) > sp.v_f(p) > 0.0
        assert sp.h_g(p) > sp.h_f(p) > 0.0
        assert sp.u_g(p) > sp.u_f(p) > 0.0
    # v_g strictly decreasing with pressure
    vgs = [sp.v_g(p * 1e6) for p in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12)]
    assert all(a > b for a, b in zip(vgs, vgs[1:], strict=False))


def test_fit_derivatives_match_finite_difference():
    """The emitted d/dp functions feed the drum Newton — verify against central FD."""
    funcs = [
        ("v_f", sp.v_f, sp.dv_f_dp),
        ("v_g", sp.v_g, sp.dv_g_dp),
        ("u_f", sp.u_f, sp.du_f_dp),
        ("u_g", sp.u_g, sp.du_g_dp),
    ]
    for p_mpa in (4.0, 6.0, 8.0, 10.0):
        p = p_mpa * 1e6
        dp = 1e3  # Pa
        for name, f, dfdp in funcs:
            fd = (f(p + dp) - f(p - dp)) / (2 * dp)
            an = dfdp(p)
            rel = abs(an - fd) / max(abs(fd), 1e-300)
            print(f"{name} at {p_mpa} MPa: analytic {an:.6e}, FD {fd:.6e}, rel {rel:.2e}")
            assert rel < 1e-5


def test_u_h_v_consistency():
    """u = h - p*v must hold for the independent fits (they were fit separately)."""
    worst = 0.0
    for p_mpa in (3.5, 6.0, 8.0, 11.5):
        p = p_mpa * 1e6
        for h, u, v in ((sp.h_f, sp.u_f, sp.v_f), (sp.h_g, sp.u_g, sp.v_g)):
            resid = abs(u(p) - (h(p) - p * v(p))) / abs(u(p))
            worst = max(worst, resid)
    print(f"u = h - p*v worst rel residual = {worst:.2e}")
    assert worst < 5e-4


def test_range_monotonicity_psat():
    ts = [30 + 5 * i + T0_K for i in range(25)]
    ps = [sp.psat(t) for t in ts]
    assert all(a < b for a, b in zip(ps, ps[1:], strict=False))
    assert math.isclose(sp.psat(100.0 + T0_K), 101.35e3, rel_tol=5e-3)
