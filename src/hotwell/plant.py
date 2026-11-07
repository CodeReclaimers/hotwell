"""Composition root: wires components, owns the state registry and the
derivative function (which solves the algebraic flow network and drum closure
internally). No fast pressure nodes are ODE states — locked design decision.

All units SI: Pa, kg, kg/s, J, K, W, rad/s, m.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from hotwell import data
from hotwell import steam_properties as sp
from hotwell.components.condenser import Condenser, CondenserParams
from hotwell.components.deaerator import Deaerator, DeaeratorParams
from hotwell.components.drum import (
    AstromBellDrum,
    AstromBellDrumParams,
    DrumOutputs,
    TwoStateDrum,
    TwoStateDrumParams,
)
from hotwell.components.loads import LoadBlock, Loads
from hotwell.components.pumps import (
    MODE_RUNNING,
    MODE_STARTING,
    G,
    PathFlowResult,
    PumpParams,
    PumpUnit,
    solve_path_flow,
)
from hotwell.components.turbine import RotorParams, Turbine, TurbineParams
from hotwell.components.valves import Actuator, ActuatorParams, valve_flow
from hotwell.control.loops import Commands
from hotwell.state import StateRegistry

PUMP_NAMES = ("cp1", "cp2", "fp1", "fp2")


@dataclass
class Discrete:
    """Discrete plant state — frozen during RK4 stages, mutated only by the
    event layer at step boundaries."""

    pump_modes: dict[str, str] = field(
        default_factory=lambda: {"cp1": "running", "cp2": "stopped",
                                 "fp1": "running", "fp2": "stopped"})
    pump_trip_reason: dict[str, str] = field(default_factory=dict)
    start_inhibited: set[str] = field(default_factory=set)
    mft: bool = False
    turbine_trip: bool = False
    safety_open: bool = False
    nonvital_connected: bool = True
    breaker_closed: bool = True
    plant_dead: bool = False
    air_ingress: float = 0.0  # Pa added to condenser pressure (scenario hook)
    # 0.4.0 M5 hidden physical faults (hotwell.faults); 1.0 = healthy.
    head_factor: dict[str, float] = field(
        default_factory=lambda: {"cp1": 1.0, "cp2": 1.0, "fp1": 1.0, "fp2": 1.0})
    cv_factor: dict[str, float] = field(
        default_factory=lambda: {"frv": 1.0, "lcv": 1.0, "makeup_valve": 1.0})
    rate_factor: dict[str, float] = field(
        default_factory=lambda: {"fw_valve": 1.0, "throttle": 1.0, "firing": 1.0})
    stuck: dict[str, float] = field(default_factory=dict)  # actuator -> held cmd (direct valves)
    eta_factor: float = 1.0
    fouling_factor: float = 1.0
    leak_design: float = 0.0  # 0.4.0 M5b tube_leak [kg/s] at design drum pressure


@dataclass(frozen=True)
class Aux:
    """Algebraic quantities computed inside one derivative evaluation."""

    p_drum: float          # [Pa]
    drum_level: float      # [m] rel NWL
    h_g_drum: float        # [J/kg]
    m_throttle: float      # [kg/s]
    m_exhaust: float       # [kg/s]
    m_relief: float        # [kg/s]
    m_peg: float           # [kg/s]
    m_cond: float          # [kg/s]
    m_fw: float            # [kg/s]
    q_fire: float          # [W] effective heat to fluid
    p_mech: float          # [W]
    p_elec: float          # [W] incl. station service
    p_station_service: float  # [W] running pump motor draw (part of p_elec)
    p_cond: float          # [Pa]
    q_cond_duty: float     # [W] (net of makeup heating, 0.4.0 M5b)
    p_damping: float       # [W] mechanical damping loss
    hw_level_rel: float    # [m]
    da_level_rel: float    # [m]
    cond_flow: PathFlowResult
    feed_flow: PathFlowResult
    # 0.4.0 M5b boundary flows (defaults keep any external Aux construction valid)
    m_makeup: float = 0.0  # [kg/s] CST -> condenser
    h_makeup: float = 0.0  # [J/kg]
    m_leak: float = 0.0    # [kg/s] drum water-space tube leak (leaves the cycle)
    h_leak: float = 0.0    # [J/kg]


def load_config(path: str | Path | None = None) -> dict:
    """Load a plant parameter YAML (defaults to the packaged baseline)."""
    src = data.baseline_config_path() if path is None else path
    return yaml.safe_load(data.read_text(src))


class Plant:
    """The wired plant. Owns components, registry, and the derivative."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        reg = StateRegistry()
        self.registry = reg

        # actuators (state order per plan section 4.1)
        act = cfg["actuators"]
        self.fw_valve = Actuator("fw_valve", ActuatorParams(**act["fw_valve"]), reg, 0.55)
        self.throttle = Actuator("throttle", ActuatorParams(**act["throttle"]), reg, 0.85)
        self.firing = Actuator("firing", ActuatorParams(**act["firing"]), reg, 0.8)

        # pumps
        pc = cfg["pumps"]
        cp = PumpParams(**pc["condensate"])
        fp = PumpParams(**pc["feed"])
        self.pumps = {
            "cp1": PumpUnit("cp1", cp, reg, 1.0),
            "cp2": PumpUnit("cp2", cp, reg, 0.0),
            "fp1": PumpUnit("fp1", fp, reg, 1.0),
            "fp2": PumpUnit("fp2", fp, reg, 0.0),
        }

        dr = cfg["drum"]
        model = dr.get("model", "two_state")
        if model == "two_state":
            self.drum: TwoStateDrum | AstromBellDrum = TwoStateDrum(
                TwoStateDrumParams(**dr["two_state"]))
        elif model == "astrom_bell":
            self.drum = AstromBellDrum(AstromBellDrumParams(**dr["astrom_bell"]))
        else:
            raise ValueError(f"unknown drum model: {model!r}")
        self.drum.register_states(reg)

        self.turbine = Turbine(TurbineParams(**cfg["turbine"]),
                               RotorParams(**cfg["rotor"]), reg)
        self.condenser = Condenser(CondenserParams(**cfg["condenser"]), reg)
        self.deaerator = Deaerator(DeaeratorParams(**cfg["deaerator"]), reg)

        ld = cfg["loads"]
        self.loads = Loads(
            LoadBlock("vital", ld["vital_p0"], ld["k_pf"]),
            LoadBlock("nonvital", ld["nonvital_p0"], ld["k_pf"]),
        )

        fire = cfg["firing"]
        self.eta_comb = fire["eta_comb"]          # [-]
        self.q_fuel_max = fire["q_fuel_max"]      # [W] fuel heat at firing.x = 1

        net = cfg["network"]
        self.z_hw = cfg["condenser"]["z_hw"]      # [m]
        self.z_da = cfg["deaerator"]["z_da"]      # [m]
        self.z_da_inlet = net["z_da_inlet"]       # [m] DA inlet above CP suction
        self.z_drum_inlet = net["z_drum_inlet"]   # [m] drum inlet above FP suction
        self.k_line_cond = net["k_line_cond"]     # [Pa/(m3/s)^2]
        self.k_line_feed = net["k_line_feed"]     # [Pa/(m3/s)^2]
        self.cv_lcv = net["cv_lcv"]               # [kg/(s*Pa^0.5)]
        self.cv_frv = net["cv_frv"]               # [kg/(s*Pa^0.5)]

        prot = cfg["safety_valve"]
        self.c_sv = prot["c_sv"]                  # [kg/(s*Pa)] relief coefficient
        self.piping_holdup = cfg["audit"]["piping_holdup"]  # [kg]

        # warm starts for the two path solves
        self._qw_cond = 0.077
        self._qw_feed = 0.092

        # motor-current display proxy references [W]
        rho_da = self.deaerator.rho
        self._p_hyd_rated = {}
        for name in PUMP_NAMES:
            p = self.pumps[name].p
            h_rated = p.h0 - p.k * p.q_rated * p.q_rated
            rho = 992.0 if name.startswith("cp") else rho_da
            self._p_hyd_rated[name] = rho * G * h_rated * p.q_rated

        self.n_states = reg.n

        # 0.4.0: calibrate turbine efficiency at the design state: design drum
        # pressure, and the condenser pressure the condenser model gives at
        # rated exhaust flow (not a separately typed 7 kPa).
        p_d = cfg["design"]["p_drum"]
        tp = self.turbine.tp
        self.turbine.set_design(p_d, self.condenser.p_cond(tp.k_t * tp.x_rated * p_d, 0.0))

        # 0.4.0 M5b makeup: CST water properties, vacuum drag-in, Cv DERIVED so the
        # valve passes capacity_design wide open at the design condenser pressure.
        mu = cfg["makeup"]
        self.mu_p_atm = mu["p_atm"]                    # [Pa]
        self.mu_h = sp.hf_t(mu["t_cst"])               # [J/kg]
        self.mu_rho = sp.rho_f_t(mu["t_cst"])          # [kg/m3]
        self.mu_head = self.mu_rho * G * mu["z_cst"]   # [Pa]
        p_c_design = self.condenser.p_cond(tp.k_t * tp.x_rated * p_d, 0.0)
        self.cv_mu = mu["capacity_design"] / (
            self.mu_p_atm + self.mu_head - p_c_design) ** 0.5  # [kg/(s*Pa^0.5)]
        self.p_design = p_d

        # design-point flows (used by steady init and the AB drum's V_sd0)
        if isinstance(self.drum, AstromBellDrum):
            p0, _, _, m_fw_r, q_fire_r = self.design_point()
            self.drum.finalize_design(p0, m_fw_r, q_fire_r, self.deaerator.h_fw)

    def design_point(self) -> tuple[float, float, float, float, float]:
        """Rated-condition flows at design pressure: (p0 [Pa], m_turb, m_peg,
        m_fw [kg/s], q_fire [W]). Same construction the steady init uses."""
        p0 = self.cfg["design"]["p_drum"]
        tp = self.turbine.tp
        m_turb = tp.k_t * tp.x_rated * p0
        p_cond = self.condenser.p_cond(m_turb, 0.0)
        h_c = sp.hf_t(sp.tsat_lowp(p_cond))
        m_peg = self.deaerator.m_pegging(m_turb, h_c, p0, sp.h_g(p0))
        m_fw = m_turb + m_peg
        q_fire = m_fw * (sp.h_g(p0) - self.deaerator.h_fw)
        return p0, m_turb, m_peg, m_fw, q_fire

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> Plant:
        return cls(load_config(path))

    # ------------------------------------------------------------------ deriv

    def deriv(self, y, cmds: Commands, disc: Discrete) -> tuple[np.ndarray, Aux]:
        """Full plant derivative at state y with commands/discrete frozen."""
        yl = y.tolist() if isinstance(y, np.ndarray) else list(y)
        ydot = [0.0] * self.n_states

        drum_out: DrumOutputs = self.drum.outputs(yl)
        p_drum = drum_out.p
        h_g = drum_out.h_steam

        x_thr = yl[self.throttle.i_x]
        m_thr = self.turbine.m_throttle(x_thr, p_drum)
        m_exh = self.turbine.m_chest_out(yl)

        p_cond = self.condenser.p_cond(m_exh, disc.air_ingress, disc.fouling_factor)
        t_c = sp.tsat_lowp(p_cond)
        h_c = sp.hf_t(t_c)
        rho_c = sp.rho_f_t(t_c)
        hw_abs = self.condenser.level_abs(yl, rho_c)

        cp1, cp2 = self.pumps["cp1"], self.pumps["cp2"]
        fp1, fp2 = self.pumps["fp1"], self.pumps["fp2"]
        hf = disc.head_factor
        res_c = solve_path_flow(
            (cp1, cp2), (yl[cp1.i_s], yl[cp2.i_s]),
            p_supply=p_cond + rho_c * G * (self.z_hw + hw_abs),
            p_demand=self.deaerator.p.p_da + rho_c * G * self.z_da_inlet,
            suction_head=self.z_hw + hw_abs, p_vap_margin=0.0,
            rho=rho_c, k_line=self.k_line_cond,
            cv=self.cv_lcv * disc.cv_factor["lcv"], x_valve=cmds.lcv_x,
            q_warm=self._qw_cond, head_factors=(hf["cp1"], hf["cp2"]))
        self._qw_cond = res_c.q_total
        m_cond = res_c.m_dot

        m_peg = self.deaerator.m_pegging(m_cond, h_c, p_drum, h_g)

        da = self.deaerator
        da_abs = da.level_abs(yl)
        rho_da = da.rho
        res_f = solve_path_flow(
            (fp1, fp2), (yl[fp1.i_s], yl[fp2.i_s]),
            p_supply=da.p.p_da + rho_da * G * (self.z_da + da_abs),
            p_demand=p_drum + rho_da * G * self.z_drum_inlet,
            suction_head=self.z_da + da_abs, p_vap_margin=0.0,
            rho=rho_da, k_line=self.k_line_feed,
            cv=self.cv_frv * disc.cv_factor["frv"], x_valve=yl[self.fw_valve.i_x],
            q_warm=self._qw_feed, head_factors=(hf["fp1"], hf["fp2"]))
        self._qw_feed = res_f.q_total
        m_fw = res_f.m_dot

        m_relief = self.c_sv * p_drum if disc.safety_open else 0.0
        # 0.4.0 M5b: makeup (direct-command valve, vacuum drag-in) and tube leak.
        m_mu = 0.0
        if cmds.mu_x > 0.0:
            m_mu = valve_flow(self.cv_mu * disc.cv_factor["makeup_valve"], cmds.mu_x,
                              self.mu_p_atm + self.mu_head - p_cond)
        m_leak = h_leak = 0.0
        if disc.leak_design > 0.0:
            m_leak = disc.leak_design * (max(p_drum, 0.0) / self.p_design) ** 0.5
            h_leak = sp.h_f(p_drum)
        q_fire = yl[self.firing.i_x] * (self.eta_comb * disc.eta_factor) * self.q_fuel_max
        m_s_total = m_thr + m_peg + m_relief
        self.drum.derivatives(yl, ydot, drum_out, q_fire, m_fw, da.h_fw, m_s_total,
                              m_leak, h_leak)

        omega = yl[self.turbine.i_omega]
        omega0 = self.turbine.rp.omega0
        p_ss = (
            self._pump_motor_power("cp1", disc.pump_modes["cp1"],
                                   res_c.q[0], res_c.head, rho_c)
            + self._pump_motor_power("cp2", disc.pump_modes["cp2"],
                                     res_c.q[1], res_c.head, rho_c)
            + self._pump_motor_power("fp1", disc.pump_modes["fp1"],
                                     res_f.q[0], res_f.head, rho_da)
            + self._pump_motor_power("fp2", disc.pump_modes["fp2"],
                                     res_f.q[1], res_f.head, rho_da))
        p_e = self.loads.p_elec(omega, omega0, disc.nonvital_connected,
                                disc.breaker_closed, p_ss)
        w_t = self.turbine.specific_work(p_drum, p_cond)
        self.turbine.deriv(yl, ydot, x_thr, p_drum, p_e, w_t)
        self.condenser.deriv(yl, ydot, m_exh, m_cond, m_mu)
        da.deriv(yl, ydot, m_cond, m_peg, m_fw)

        for name in PUMP_NAMES:
            self.pumps[name].deriv(yl, ydot, disc.pump_modes[name])
        rf, st = disc.rate_factor, disc.stuck
        self.fw_valve.deriv(yl, ydot, cmds.fw_cmd, "fw_valve" in st, rf["fw_valve"])
        self.throttle.deriv(yl, ydot, cmds.throttle_cmd, "throttle" in st, rf["throttle"])
        self.firing.deriv(yl, ydot, cmds.firing_cmd, "firing" in st, rf["firing"])

        h_exh = h_g - w_t
        aux = Aux(
            p_drum=p_drum, drum_level=drum_out.level, h_g_drum=h_g,
            m_throttle=m_thr, m_exhaust=m_exh, m_relief=m_relief,
            m_peg=m_peg, m_cond=m_cond, m_fw=m_fw, q_fire=q_fire,
            p_mech=self.turbine.p_mech(yl, w_t), p_elec=p_e,
            p_station_service=p_ss, p_cond=p_cond,
            q_cond_duty=self.condenser.q_cond(m_exh, h_exh, p_cond, m_mu, self.mu_h),
            p_damping=self.turbine.rp.d_m * (omega - omega0) * omega,
            hw_level_rel=hw_abs - self.condenser.p.hw_level_nominal,
            da_level_rel=da_abs - da.p.level_nominal,
            cond_flow=res_c, feed_flow=res_f,
            m_makeup=m_mu, h_makeup=self.mu_h, m_leak=m_leak, h_leak=h_leak,
        )
        return np.asarray(ydot), aux

    # ------------------------------------------------------------------ truth

    def total_water_mass(self, y, aux: Aux) -> float:
        """Total tracked water inventory [kg] (drum + hotwell + DA + chest +
        fixed piping holdup)."""
        yl = y.tolist() if isinstance(y, np.ndarray) else list(y)
        return (self.drum.mass(yl) + yl[self.condenser.i_m] + yl[self.deaerator.i_m]
                + self.turbine.chest_holdup(yl) + self.piping_holdup)

    def _pump_current(self, name: str, s: float, q: float, head: float,
                      rho: float) -> float:
        """Motor current display proxy [A], proportional to hydraulic power."""
        if s < 0.05:
            return 0.0
        p_hyd = rho * G * head * q
        p = self.pumps[name].p
        return p.i_rated * (0.25 + 0.75 * p_hyd / self._p_hyd_rated[name])

    def _pump_motor_power(self, name: str, mode: str, q: float, head: float,
                          rho: float) -> float:
        """Motor electrical draw [W] — station-service load on the islanded
        bus. Same 25% no-load floor + hydraulic-power-proportional shape as
        the ammeter proxy, so wattage and current agree by construction. A
        stopped or tripped pump draws nothing, even while coasting down (its
        contactor is open); motor inrush at start is not modeled."""
        if mode not in (MODE_STARTING, MODE_RUNNING):
            return 0.0
        p = self.pumps[name].p
        if p.p_motor_rated <= 0.0:
            return 0.0
        p_hyd = rho * G * head * q
        return p.p_motor_rated * (0.25 + 0.75 * p_hyd / self._p_hyd_rated[name])

    def truth(self, t: float, y, aux: Aux, disc: Discrete) -> dict[str, float]:
        """Assemble the truth value for every instrument in the observation spec."""
        yl = y.tolist() if isinstance(y, np.ndarray) else list(y)
        rho_c = sp.rho_f_t(sp.tsat_lowp(aux.p_cond))
        rho_da = self.deaerator.rho
        rc, rf = aux.cond_flow, aux.feed_flow
        return {
            "drum_pressure": aux.p_drum,
            "drum_level": aux.drum_level,
            "steam_flow": aux.m_throttle,
            "feed_flow": aux.m_fw,
            "condensate_flow": aux.m_cond,
            "chest_pressure": yl[self.turbine.i_pch],
            "cond_pressure": aux.p_cond,
            "hotwell_level": aux.hw_level_rel,
            "da_level": aux.da_level_rel,
            "da_pressure": self.deaerator.p.p_da,
            "frequency": yl[self.turbine.i_omega] / 6.283185307179586,
            "mw_out": aux.p_elec,
            "cp1_current": self._pump_current("cp1", yl[self.pumps["cp1"].i_s],
                                              rc.q[0], rc.head, rho_c),
            "cp2_current": self._pump_current("cp2", yl[self.pumps["cp2"].i_s],
                                              rc.q[1], rc.head, rho_c),
            "fp1_current": self._pump_current("fp1", yl[self.pumps["fp1"].i_s],
                                              rf.q[0], rf.head, rho_da),
            "fp2_current": self._pump_current("fp2", yl[self.pumps["fp2"].i_s],
                                              rf.q[1], rf.head, rho_da),
            "fw_valve_pos": yl[self.fw_valve.i_x],
            "throttle_pos": yl[self.throttle.i_x],
            "firing_rate": yl[self.firing.i_x],
            "da_lcv_pos": 0.0,  # overwritten by simulator (command, not a state)
            "fp1_npsh_margin": rf.margin[0],
            "fp2_npsh_margin": rf.margin[1],
            "makeup_flow": aux.m_makeup,
            "cp1_npsh_margin": aux.cond_flow.margin[0],
            "cp2_npsh_margin": aux.cond_flow.margin[1],
        }
