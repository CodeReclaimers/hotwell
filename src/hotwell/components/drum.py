"""Drum boiler: stable interface (phase-agnostic) + phase-1 two-state model.

Interface contract (section 5.2 of the plan): inputs are effective firing heat
Q_fire [W], feed flow m_fw [kg/s], feed enthalpy h_fw [J/kg], and steam flow
drawn m_s [kg/s]; outputs are drum pressure p [Pa], drum level l [m, relative
to normal water level NWL = 0], and steam enthalpy h_g(p) [J/kg]. The M4
AstromBellDrum swap must change nothing outside this file.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

from hotwell.state import StateRegistry


@dataclass(frozen=True)
class DrumOutputs:
    """Algebraic outputs of the drum closure at one state evaluation."""

    p: float        # drum pressure [Pa]
    level: float    # drum level relative to NWL [m]
    h_steam: float  # saturated steam enthalpy h_g(p) [J/kg]


class DrumBoiler(ABC):
    """Stable drum-boiler interface; concrete models own their ODE states."""

    @abstractmethod
    def register_states(self, reg: StateRegistry) -> None:
        """Declare this model's continuous states (indices kept internally)."""

    @abstractmethod
    def outputs(self, y: np.ndarray) -> DrumOutputs:
        """Solve the model's algebraic closure at state y; warm-started, cheap."""

    @abstractmethod
    def derivatives(self, y: np.ndarray, ydot: np.ndarray, out: DrumOutputs,
                    q_fire: float, m_fw: float, h_fw: float, m_s: float,
                    m_leak: float = 0.0, h_leak: float = 0.0) -> None:
        """Write d/dt of this model's states into ydot.

        q_fire [W] effective heat to fluid; m_fw [kg/s] feed flow; h_fw [J/kg]
        feed enthalpy; m_s [kg/s] total steam drawn (turbine + auxiliary + relief);
        m_leak [kg/s] saturated liquid lost from the water space at h_leak [J/kg]
        (0.4.0 M5b tube_leak).
        """

    @abstractmethod
    def mass(self, y: list[float]) -> float:
        """Total drum-system fluid mass [kg] (for the mass audit)."""

    @abstractmethod
    def steady_init(self, y: np.ndarray, p0: float, m_fw: float,
                    q_fire: float) -> None:
        """Write this model's equilibrium states at (p0, rated flows) into y —
        the analytic guess polished by the steady-state root solve."""

    @abstractmethod
    def state_indices(self) -> list[int]:
        """Registered state indices, for the steady-state residual rows."""

    @abstractmethod
    def deriv_scales(self) -> list[float]:
        """Characteristic derivative magnitudes per state (residual scaling)."""


@dataclass(frozen=True)
class TwoStateDrumParams:
    v_total: float      # drum+riser fluid volume [m3]
    v_liq_nwl: float    # liquid volume at normal water level [m3]
    a_waterplane: float  # effective waterplane area [m2] (vertical-cylinder equiv.)
    p_min: float = 3.2e6   # closure clamp, low [Pa] (fit range guard)
    p_max: float = 11.8e6  # closure clamp, high [Pa]


class TwoStateDrum(DrumBoiler):
    """Phase-1 drum: saturated equilibrium mixture (M, U) in fixed volume.

    dM/dt = m_fw - m_s;  dU/dt = q_fire + m_fw*h_fw - m_s*h_g(p).
    Closure: find (p, x) with M*v_mix(p,x) = V and M*u_mix(p,x) = U, damped
    Newton warm-started from the previous solve. Level is monotone in liquid
    volume (no shrink/swell — accepted phase-1 limitation, see T9).
    """

    def __init__(self, params: TwoStateDrumParams) -> None:
        self.p = params
        self.i_m = -1
        self.i_u = -1
        self._p_warm = 8.0e6
        self._x_warm = 0.05

    def register_states(self, reg: StateRegistry) -> None:
        # initials are placeholders; initialize_steady_state overwrites them
        self.i_m = reg.register("drum.M", 10.7e3, "kg", 4.0e3)
        self.i_u = reg.register("drum.U", 1.47e10, "J", 4.0e9)

    def solve_closure(self, m: float, u: float) -> tuple[float, float]:
        """Return (p [Pa], quality x [-]) with M*v_mix = V, M*u_mix = U."""
        from hotwell import steam_properties as sp

        v_spec = self.p.v_total / m
        u_spec = u / m
        p = self._p_warm
        x = self._x_warm
        for _ in range(30):
            vf = sp.v_f(p)
            vg = sp.v_g(p)
            uf = sp.u_f(p)
            ug = sp.u_g(p)
            vfg = vg - vf
            ufg = ug - uf
            f1 = vf + x * vfg - v_spec
            f2 = uf + x * ufg - u_spec
            # Jacobian
            j11 = sp.dv_f_dp(p) + x * (sp.dv_g_dp(p) - sp.dv_f_dp(p))
            j12 = vfg
            j21 = sp.du_f_dp(p) + x * (sp.du_g_dp(p) - sp.du_f_dp(p))
            j22 = ufg
            det = j11 * j22 - j12 * j21
            dp = (-f1 * j22 + f2 * j12) / det
            dx = (-f2 * j11 + f1 * j21) / det
            # damping: limit pressure step to 1 MPa, x step to 0.2
            if dp > 1e6:
                dp = 1e6
            elif dp < -1e6:
                dp = -1e6
            if dx > 0.2:
                dx = 0.2
            elif dx < -0.2:
                dx = -0.2
            p += dp
            x += dx
            if p < self.p.p_min:
                p = self.p.p_min
            elif p > self.p.p_max:
                p = self.p.p_max
            if x < 1e-6:
                x = 1e-6
            elif x > 0.9:
                x = 0.9
            if abs(dp) < 1e-3 and abs(dx) < 1e-9:
                break
        self._p_warm = p
        self._x_warm = x
        return p, x

    def outputs(self, y: np.ndarray | list[float]) -> DrumOutputs:
        from hotwell import steam_properties as sp

        m = y[self.i_m]
        u = y[self.i_u]
        p, x = self.solve_closure(m, u)
        v_liq = m * (1.0 - x) * sp.v_f(p)
        level = (v_liq - self.p.v_liq_nwl) / self.p.a_waterplane
        return DrumOutputs(p=p, level=level, h_steam=sp.h_g(p))

    def derivatives(self, y: list[float], ydot: list[float], out: DrumOutputs,
                    q_fire: float, m_fw: float, h_fw: float, m_s: float,
                    m_leak: float = 0.0, h_leak: float = 0.0) -> None:
        """0.4.0 M5b: m_leak [kg/s] of saturated liquid at h_leak leaves the
        water space (tube_leak)."""
        ydot[self.i_m] = m_fw - m_s - m_leak
        ydot[self.i_u] = q_fire + m_fw * h_fw - m_s * out.h_steam - m_leak * h_leak

    def mass(self, y: list[float]) -> float:
        return y[self.i_m]

    def steady_init(self, y: np.ndarray, p0: float, m_fw: float,
                    q_fire: float) -> None:
        from hotwell import steam_properties as sp
        v_liq = self.p.v_liq_nwl
        v_stm = self.p.v_total - v_liq
        m = v_liq / sp.v_f(p0) + v_stm / sp.v_g(p0)
        x_q = (v_stm / sp.v_g(p0)) / m
        y[self.i_m] = m
        y[self.i_u] = m * (sp.u_f(p0) + x_q * (sp.u_g(p0) - sp.u_f(p0)))

    def state_indices(self) -> list[int]:
        return [self.i_m, self.i_u]

    def deriv_scales(self) -> list[float]:
        return [1.0, 1e6]  # kg/s, W


G = 9.80665  # m/s^2


@dataclass(frozen=True)
class AstromBellDrumParams:
    """Astrom & Bell (Automatica 36, 2000) fourth-order drum model parameters.

    Geometry/masses are the paper's P16-G16 values and are multiplied by
    `scale` (the steam-flow ratio between our design point and the paper
    plant's estimated full-load steam flow) at construction — see HANDOFF.
    """

    scale: float       # steam-flow ratio [-]
    v_d: float         # drum volume [m3] (paper value, pre-scale)
    v_r: float         # riser volume [m3]
    v_dc: float        # downcomer volume [m3]
    a_d: float         # drum wet area at operating level [m2]
    m_t: float         # total metal mass [kg]
    m_r: float         # riser metal mass [kg]
    m_d: float         # drum metal mass [kg] (inferred; see HANDOFF)
    cp_metal: float    # metal specific heat [J/(kg*K)]
    k_friction: float  # downcomer-riser loop friction coefficient [-]
    a_dc: float        # downcomer flow area [m2] (calibrated with k)
    beta: float        # empirical steam-flow distribution parameter [-]
    t_d: float         # residence time of steam in drum [s]
    vsd_nom: float     # nominal steam volume under the level [m3], pre-scale
    p_min: float = 3.2e6   # property-fit range guard [Pa]
    p_max: float = 11.8e6


class AstromBellDrum(DrumBoiler):
    """Four-state drum model: p, V_wt, alpha_r, V_sd (eq. 24 of the paper).

    States: drum pressure [Pa], total water volume [m3], riser-exit steam
    mass quality [-], steam volume under the liquid level [m3]. Exhibits
    shrink/swell (T9). finalize_design() must be called once after
    construction to fix V_sd0 and the level reference at the design point.
    """

    def __init__(self, params: AstromBellDrumParams) -> None:
        s = params.scale
        self.p = params
        self.vd = params.v_d * s
        self.vr = params.v_r * s
        self.vdc = params.v_dc * s
        self.vt = self.vd + self.vr + self.vdc
        self.ad = params.a_d * s
        self.adc = params.a_dc * s
        self.mt = params.m_t * s
        self.mr = params.m_r * s
        self.md = params.m_d * s
        self.cp = params.cp_metal
        self.vsd_nom = params.vsd_nom * s
        # fixed at finalize_design():
        self.vsd0 = 0.0        # V_sd^0 of eq. (18) [m3]
        self.ref_below = 0.0   # nominal (V_wd + V_sd) at level 0 [m3]
        self.vwt_nom = 0.0
        self.ar_nom = 0.05
        self.i_p = -1
        self.i_vwt = -1
        self.i_ar = -1
        self.i_vsd = -1

    def register_states(self, reg: StateRegistry) -> None:
        self.i_p = reg.register("drum.p", 8.0e6, "Pa", 4.0e6)
        self.i_vwt = reg.register("drum.Vwt", 45.0, "m3", 15.0)
        self.i_ar = reg.register("drum.alpha_r", 0.1, "-", 0.15)
        self.i_vsd = reg.register("drum.Vsd", 4.6, "m3", 5.0)

    # ------------------------------------------------------------- properties

    def _props(self, p: float):
        """Saturation properties + d/dp at (clamped) pressure p."""
        from hotwell import steam_properties as sp
        if p < self.p.p_min:
            p = self.p.p_min
        elif p > self.p.p_max:
            p = self.p.p_max
        vf = sp.v_f(p)
        vg = sp.v_g(p)
        rw = 1.0 / vf
        rs = 1.0 / vg
        drw = -sp.dv_f_dp(p) * rw * rw
        drs = -sp.dv_g_dp(p) * rs * rs
        return (p, rw, rs, sp.h_f(p), sp.h_g(p), drw, drs,
                sp.dh_f_dp(p), sp.dh_g_dp(p), sp.dtsat_dp(p))

    @staticmethod
    def _void(ar: float, rw: float, rs: float, drw: float, drs: float):
        """Mean void fraction (eq. 12) and its partials (eq. 26)."""
        from math import log
        if ar < 1e-4:
            ar = 1e-4
        eta = ar * (rw - rs) / rs
        ln1 = log(1.0 + eta)
        av = rw / (rw - rs) * (1.0 - rs / ((rw - rs) * ar) * ln1)
        dav_dp = (1.0 / (rw - rs) ** 2) * (rw * drs - rs * drw) * (
            1.0 + rw / rs / (1.0 + eta) - (rs + rw) / (eta * rs) * ln1)
        dav_dar = rw / (rs * eta) * (ln1 / eta - 1.0 / (1.0 + eta))
        return eta, av, dav_dp, dav_dar

    def _qdc(self, av: float, rw: float, rs: float) -> float:
        """Downcomer circulation flow [kg/s], eq. (15)."""
        from math import sqrt
        arg = 2.0 * rw * self.adc * (rw - rs) * G * av * self.vr / self.p.k_friction
        return sqrt(arg) if arg > 0.0 else 0.0

    # ---------------------------------------------------------- design point

    def finalize_design(self, p0: float, m_fw: float, q_fire: float,
                        h_fw: float) -> None:
        """Fix V_sd0 and the level reference from the design-point equilibrium
        (paper section 4.8): Q = alpha_r*h_c*q_dc solved for alpha_r by
        bisection; V_sd0 from the V_sd equilibrium with our (very) subcooled
        feed; level reference = half-full drum below the surface."""
        _, rw, rs, hw, hs, drw, drs, _, _, _ = self._props(p0)
        hc = hs - hw
        lo, hi = 1e-4, 0.6
        for _ in range(80):
            ar = 0.5 * (lo + hi)
            _, av, _, _ = self._void(ar, rw, rs, drw, drs)
            if ar * hc * self._qdc(av, rw, rs) < q_fire:
                lo = ar
            else:
                hi = ar
        self.ar_nom = ar = 0.5 * (lo + hi)
        _, av, _, _ = self._void(ar, rw, rs, drw, drs)
        self.vsd0 = self.vsd_nom + self.p.t_d * (hw - h_fw) * m_fw / (rs * hc)
        self.ref_below = 0.5 * self.vd
        vwd_nom = self.ref_below - self.vsd_nom
        self.vwt_nom = vwd_nom + self.vdc + (1.0 - av) * self.vr

    def steady_init(self, y: np.ndarray, p0: float, m_fw: float,
                    q_fire: float) -> None:
        y[self.i_p] = p0
        y[self.i_vwt] = self.vwt_nom
        y[self.i_ar] = self.ar_nom
        y[self.i_vsd] = self.vsd_nom

    # -------------------------------------------------------------- interface

    def outputs(self, y: list[float]) -> DrumOutputs:
        from hotwell import steam_properties as sp
        p = y[self.i_p]
        _, rw, rs, _, _, drw, drs, _, _, _ = self._props(p)
        _, av, _, _ = self._void(y[self.i_ar], rw, rs, drw, drs)
        vwd = y[self.i_vwt] - self.vdc - (1.0 - av) * self.vr
        level = (vwd + y[self.i_vsd] - self.ref_below) / self.ad
        return DrumOutputs(p=p, level=level, h_steam=sp.h_g(p))

    def derivatives(self, y: list[float], ydot: list[float], out: DrumOutputs,
                    q_fire: float, m_fw: float, h_fw: float, m_s: float,
                    m_leak: float = 0.0, h_leak: float = 0.0) -> None:
        """Eq. (24) of the paper, solved sequentially (lower triangular).
        0.4.0 M5b: a water-space liquid leak enters only the GLOBAL mass (r1) and
        energy (r2) balances; the riser (r3) and sub-surface steam (r4) rows are
        unchanged (valid for a drum/downcomer water-space leak, not a riser leak)."""
        p = y[self.i_p]
        vwt = y[self.i_vwt]
        ar = y[self.i_ar]
        vsd = y[self.i_vsd]
        _, rw, rs, hw, hs, drw, drs, dhw, dhs, dts = self._props(p)
        hc = hs - hw
        vst = self.vt - vwt
        _, av, dav_dp, dav_dar = self._void(ar, rw, rs, drw, drs)
        qdc = self._qdc(av, rw, rs)
        vwd = vwt - self.vdc - (1.0 - av) * self.vr
        cp = self.cp

        e11 = rw - rs
        e12 = vwt * drw + vst * drs
        e21 = rw * hw - rs * hs
        e22 = (vwt * (hw * drw + rw * dhw) + vst * (hs * drs + rs * dhs)
               - self.vt + self.mt * cp * dts)
        e32 = ((rw * dhw - ar * hc * drw) * (1.0 - av) * self.vr
               + ((1.0 - ar) * hc * drs + rs * dhs) * av * self.vr
               + (rs + (rw - rs) * ar) * hc * self.vr * dav_dp
               - self.vr + self.mr * cp * dts)
        e33 = ((1.0 - ar) * rs + ar * rw) * hc * self.vr * dav_dar
        b1 = ar * (1.0 + self.p.beta) * self.vr
        e42 = (vsd * drs
               + (rs * vsd * dhs + rw * vwd * dhw - vsd - vwd
                  + self.md * cp * dts) / hc
               + b1 * (av * drs + (1.0 - av) * drw + (rs - rw) * dav_dp))
        e43 = ar * (1.0 + self.p.beta) * (rs - rw) * self.vr * dav_dar
        e44 = rs

        r1 = m_fw - m_s - m_leak
        r2 = q_fire + m_fw * h_fw - m_s * hs - m_leak * h_leak
        r3 = q_fire - ar * hc * qdc
        r4 = rs / self.p.t_d * (self.vsd0 - vsd) + (h_fw - hw) / hc * m_fw

        det = e11 * e22 - e12 * e21
        dvwt = (e22 * r1 - e12 * r2) / det
        dp = (e11 * r2 - e21 * r1) / det
        dar = (r3 - e32 * dp) / e33
        dvsd = (r4 - e42 * dp - e43 * dar) / e44

        ydot[self.i_p] = dp
        ydot[self.i_vwt] = dvwt
        ydot[self.i_ar] = dar
        ydot[self.i_vsd] = dvsd

    def mass(self, y: list[float]) -> float:
        _, rw, rs, _, _, _, _, _, _, _ = self._props(y[self.i_p])
        return rw * y[self.i_vwt] + rs * (self.vt - y[self.i_vwt])

    def state_indices(self) -> list[int]:
        return [self.i_p, self.i_vwt, self.i_ar, self.i_vsd]

    def deriv_scales(self) -> list[float]:
        return [1e3, 0.01, 1e-4, 0.01]  # Pa/s, m3/s, 1/s, m3/s
