"""Centrifugal pump units and the quasi-static path flow solve.

Pump head curve: h = H0*s^2 - K*q^2  [m], s = speed fraction, q = per-pump
volumetric flow [m3/s]. Spin-up/coast-down is a first-order lag on s. Two
identical pumps in parallel split flow by equal delivered head (closed form);
a stopped or deadheaded pump's branch carries zero flow (check valve).

Cavitation: while NPSH margin < 0, delivered head is degraded by the smooth
factor 1/(1 + (margin/0.5)^2). The factor uses the flow split computed from
undegraded curves within the same residual evaluation (documented
approximation; exact self-consistency is not needed at this fidelity).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from hotwell.state import StateRegistry

G = 9.80665  # m/s^2

MODE_STOPPED = "stopped"
MODE_STARTING = "starting"
MODE_RUNNING = "running"
MODE_TRIPPED = "tripped"


@dataclass(frozen=True)
class PumpParams:
    q_rated: float   # rated volumetric flow [m3/s]
    h0: float        # shutoff head at s=1 [m]
    k: float         # curve coefficient [m/(m3/s)^2]
    tau: float       # spin-up/coast-down time constant [s]
    npsh_a: float    # NPSH required at zero flow [m]
    npsh_b: float    # NPSH required flow coefficient [m/(m3/s)^2]
    k_suction: float  # individual suction line friction head [m/(m3/s)^2]
    i_rated: float   # motor current at rated hydraulic power [A] (display proxy)
    rated_fraction: float = 1.0  # per-pump rated fraction of service flow


class PumpUnit:
    """One pump: continuous speed state + curve/NPSH helpers.

    Discrete mode lives in the simulator's Discrete container; this class
    only maps mode -> s_cmd and integrates the speed lag.
    """

    def __init__(self, name: str, params: PumpParams, reg: StateRegistry,
                 initial_s: float = 0.0) -> None:
        self.name = name
        self.p = params
        self.i_s = reg.register(f"{name}.s", initial_s, "-", 1.0)

    @staticmethod
    def s_cmd(mode: str) -> float:
        return 1.0 if mode in (MODE_STARTING, MODE_RUNNING) else 0.0

    def deriv(self, y: list[float], ydot: list[float], mode: str) -> None:
        ydot[self.i_s] = (self.s_cmd(mode) - y[self.i_s]) / self.p.tau

    def npsh_required(self, q: float) -> float:
        """NPSH required [m] at per-pump flow q [m3/s]."""
        return self.p.npsh_a + self.p.npsh_b * q * q


@dataclass(frozen=True)
class PathFlowResult:
    """Solved path flow and per-pump detail for one flow network path."""

    m_dot: float      # total mass flow [kg/s]
    q_total: float    # total volumetric flow [m3/s]
    q: tuple[float, float]        # per-pump volumetric flow [m3/s]
    head: float       # common delivered pump head [m]
    margin: tuple[float, float]   # per-pump NPSH margin [m]
    cav: tuple[float, float]      # per-pump head degradation factor [-]


def _cav_factor(margin: float) -> float:
    """Smooth head degradation: 1 above margin 0, falling below (C1 at 0)."""
    if margin >= 0.0:
        return 1.0
    r = margin / 0.5
    return 1.0 / (1.0 + r * r)


def _split(a1: float, b1: float, a2: float, b2: float, q_tot: float) -> tuple[float, float]:
    """Split q_tot between parallel pumps with head curves a_i - b_i q^2 at
    equal delivered head; branches clamp at zero flow (check valves)."""
    if q_tot <= 0.0:
        return 0.0, 0.0
    if a2 <= 0.0:
        return q_tot, 0.0
    if a1 <= 0.0:
        return 0.0, q_tot
    db = b1 - b2
    if abs(db) < 1e-9 * max(b1, b2):
        # equal resistance: a1 - b q1^2 = a2 - b (Q-q1)^2
        q1 = 0.5 * (q_tot + (a1 - a2) / (b1 * q_tot))
    else:
        # (b1-b2) q1^2 + 2 b2 Q q1 - (b2 Q^2 + a1 - a2) = 0
        disc = b2 * b2 * q_tot * q_tot + db * (b2 * q_tot * q_tot + a1 - a2)
        if disc < 0.0:
            disc = 0.0
        q1 = (-b2 * q_tot + sqrt(disc)) / db
    if q1 < 0.0:
        q1 = 0.0
    elif q1 > q_tot:
        q1 = q_tot
    return q1, q_tot - q1


def solve_path_flow(
    pumps: tuple[PumpUnit, PumpUnit],
    speeds: tuple[float, float],
    p_supply: float,     # upstream reservoir pressure incl. its elevation term [Pa]
    p_demand: float,     # downstream pressure incl. its elevation term [Pa]
    suction_head: float,  # static + level head above pump suction [m]
    p_vap_margin: float,  # (p_reservoir - p_vap)/(rho g) [m]; 0 for saturated source
    rho: float,          # liquid density [kg/m3]
    k_line: float,       # discharge line friction [Pa/(m3/s)^2]
    cv: float,           # downstream valve coefficient [kg/(s*Pa^0.5)]
    x_valve: float,      # downstream valve position [-]
    q_warm: float,       # warm-start total flow [m3/s]
) -> PathFlowResult:
    """Solve the quasi-static path flow (scalar root in total flow Q).

    Residual: p_supply + rho*g*head_pump(Q) - k_line*Q^2 - dp_valve(Q) - p_demand,
    monotone decreasing in Q => unique root; bisection-safeguarded secant,
    warm-started. Returns zero flow if the path cannot flow forward (check valve).
    """
    pg = rho * G
    x_eff = x_valve if x_valve > 1e-4 else 1e-4
    rv = rho / (cv * x_eff)  # dp_valve = (rv*Q)^2
    rv2 = rv * rv

    def detail(q_tot: float) -> tuple[float, float, float, float, float, float, float]:
        s1, s2 = speeds
        a1u = pumps[0].p.h0 * s1 * s1
        a2u = pumps[1].p.h0 * s2 * s2
        q1, q2 = _split(a1u, pumps[0].p.k, a2u, pumps[1].p.k, q_tot)
        m1 = p_vap_margin + suction_head - pumps[0].p.k_suction * q1 * q1 \
            - pumps[0].npsh_required(q1)
        m2 = p_vap_margin + suction_head - pumps[1].p.k_suction * q2 * q2 \
            - pumps[1].npsh_required(q2)
        c1 = _cav_factor(m1)
        c2 = _cav_factor(m2)
        # degraded curves, re-split, common head
        a1, b1 = c1 * a1u, c1 * pumps[0].p.k
        a2, b2 = c2 * a2u, c2 * pumps[1].p.k
        q1, q2 = _split(a1, b1, a2, b2, q_tot)
        if q1 > 0.0:
            head = a1 - b1 * q1 * q1
        elif q2 > 0.0:
            head = a2 - b2 * q2 * q2
        else:
            head = max(a1, a2, 0.0)
        return head, q1, q2, m1, m2, c1, c2

    def resid(q_tot: float) -> float:
        head = detail(q_tot)[0]
        return p_supply + pg * head - k_line * q_tot * q_tot - rv2 * q_tot * q_tot - p_demand

    r0 = resid(0.0)
    if r0 <= 0.0:
        head, q1, q2, m1, m2, c1, c2 = detail(0.0)
        return PathFlowResult(0.0, 0.0, (0.0, 0.0), head, (m1, m2), (c1, c2))

    q_hi = 3.0 * (pumps[0].p.q_rated + pumps[1].p.q_rated)
    lo, hi = 0.0, q_hi
    q = q_warm if 0.0 < q_warm < q_hi else 0.5 * q_hi
    rq = resid(q)
    for _ in range(60):
        if rq > 0.0:
            lo = q
        else:
            hi = q
        # secant step using bracket endpoints' freshest values via derivative estimate
        dq = 1e-7 * q_hi
        drdq = (resid(q + dq) - rq) / dq
        q_new = q - rq / drdq if drdq < 0.0 else 0.5 * (lo + hi)
        if not (lo < q_new < hi):
            q_new = 0.5 * (lo + hi)
        if abs(q_new - q) < 1e-12 * q_hi:
            q = q_new
            break
        q = q_new
        rq = resid(q)
        if abs(rq) < 1e-6 * max(abs(p_demand), 1e5):
            break
    head, q1, q2, m1, m2, c1, c2 = detail(q)
    return PathFlowResult(rho * q, q, (q1, q2), head, (m1, m2), (c1, c2))
