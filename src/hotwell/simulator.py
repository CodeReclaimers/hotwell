"""Step loop: RK4 integration, strict step sequencing, steady-state init.

Step sequence (plan section 3.2, strict order):
  1. apply actions (M2)  2. controllers (previous step's sensed obs)
  3. RK4 with discrete+commands frozen  4. event layer  5. sensors
  6. historian/audit.

Determinism: one numpy.random.Generator owned here (no stochastic elements
are active in phase 1, but all future randomness must flow from it).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.optimize import root

from hotwell.audit import AuditAccumulator, AuditReport
from hotwell.components.pumps import MODE_RUNNING, MODE_STARTING
from hotwell.control.loops import Commands, ControlSystem, GovernorParams
from hotwell.control.pid import PIParams
from hotwell.plant import PUMP_NAMES, Aux, Discrete, Plant, load_config
from hotwell.sensors import Observation, SensorBank

DT = 0.05  # s — fixed step, locked decision
TWO_PI = 6.283185307179586


def _pi_params(d: dict) -> PIParams:
    return PIParams(kp=d["kp"], ki=d["ki"], lo=d["lo"], hi=d["hi"],
                    t_track=d["t_track"])


class Simulator:
    """Owns plant, controllers, discrete state, sensors, audit, and the clock."""

    def __init__(self, config: dict | str | Path | None = None,
                 seed: int = 0) -> None:
        cfg = config if isinstance(config, dict) else load_config(config)
        self.cfg = cfg
        self.plant = Plant(cfg)
        self.rng = np.random.default_rng(seed)
        self.dt = DT
        self.t = 0.0
        self.y = self.plant.registry.initial_vector()
        self.disc = Discrete()
        self.sensors = SensorBank()
        self.audit_acc = AuditAccumulator()

        c = cfg["control"]
        rp = self.plant.turbine.rp
        self.control = ControlSystem(
            gov=GovernorParams(droop=c["governor"]["droop"],
                               p_rated=cfg["design"]["p_rated"],
                               f0=rp.f0,
                               x_rated=self.plant.turbine.tp.x_rated),
            level_pi=_pi_params(c["drum_level"]), level_sp=0.0,
            pressure_pi=_pi_params(c["drum_pressure"]),
            pressure_sp=cfg["design"]["p_drum"],
            da_pi=_pi_params(c["da_level"]), da_sp=0.0,
        )
        self.commands = Commands(0.55, 0.85, 0.8, 0.6)
        self.last_obs: Observation | None = None
        self.last_aux: Aux | None = None
        self._sv_open_p = cfg["safety_valve"]["p_open"]
        self._sv_reseat_p = cfg["safety_valve"]["p_reseat"]

    # ---------------------------------------------------------------- stepping

    def _rk4(self) -> tuple[np.ndarray, Aux]:
        """One RK4 step with commands/discrete frozen; returns new y and the
        aux recomputed at the accepted state (for sensing/audit)."""
        f = self.plant.deriv
        y, dt, cmds, disc = self.y, self.dt, self.commands, self.disc
        k1, _ = f(y, cmds, disc)
        k2, _ = f(y + 0.5 * dt * k1, cmds, disc)
        k3, _ = f(y + 0.5 * dt * k2, cmds, disc)
        k4, _ = f(y + dt * k3, cmds, disc)
        y_new = y + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        _, aux = f(y_new, cmds, disc)
        return y_new, aux

    def _event_layer(self, aux: Aux) -> None:
        """Discrete-state updates at the step boundary (M1 subset: position
        clamps, pump start completion, safety-valve hysteresis, plant-dead)."""
        p = self.plant
        y = self.y
        for a in (p.fw_valve, p.throttle, p.firing):
            if y[a.i_x] < 0.0:
                y[a.i_x] = 0.0
            elif y[a.i_x] > 1.0:
                y[a.i_x] = 1.0
        for name in PUMP_NAMES:
            pu = p.pumps[name]
            if y[pu.i_s] < 0.0:
                y[pu.i_s] = 0.0
            if self.disc.pump_modes[name] == MODE_STARTING and y[pu.i_s] >= 0.95:
                self.disc.pump_modes[name] = MODE_RUNNING
        if not self.disc.safety_open and aux.p_drum > self._sv_open_p:
            self.disc.safety_open = True
        elif self.disc.safety_open and aux.p_drum < self._sv_reseat_p:
            self.disc.safety_open = False
        all_pumps_stopped = all(
            self.disc.pump_modes[n] in ("stopped", "tripped") for n in PUMP_NAMES)
        if self.disc.mft and all_pumps_stopped:
            self.disc.plant_dead = True

    def _observe(self, aux: Aux) -> Observation:
        truth = self.plant.truth(self.t, self.y, aux, self.disc)
        truth["da_lcv_pos"] = self.commands.lcv_x
        values = self.sensors.sample(self.t, truth)
        indications = {
            f"{n}_running": self.disc.pump_modes[n] == MODE_RUNNING
            for n in PUMP_NAMES
        }
        indications.update({
            f"{n}_tripped": self.disc.pump_modes[n] == "tripped" for n in PUMP_NAMES
        })
        indications.update({
            "mft": self.disc.mft,
            "turbine_trip": self.disc.turbine_trip,
            "safety_valve_open": self.disc.safety_open,
            "nonvital_connected": self.disc.nonvital_connected,
            "breaker_closed": self.disc.breaker_closed,
        })
        return Observation(t=self.t, values=values, alarms=[],
                           indications=indications,
                           plant_dead=self.disc.plant_dead)

    def step(self, actions: dict | None = None) -> Observation:
        """Advance one step (plan section 3.2 order); returns the observation."""
        # 1. actions — M2
        # 2. controllers on previous sensed observation
        assert self.last_obs is not None, "call initialize_steady_state first"
        self.commands = self.control.update(self.last_obs.values, self.dt)
        # 3. integrate
        y_new, aux = self._rk4()
        self.y = y_new
        self.t += self.dt
        # 4. events
        self._event_layer(aux)
        # 5. sensors
        obs = self._observe(aux)
        # 6. audit (historian in M2)
        self.audit_acc.accumulate(aux.m_relief, self.dt)
        self.last_obs = obs
        self.last_aux = aux
        return obs

    def run(self, until: float) -> Observation:
        """Step until simulated time `until` [s] or plant death."""
        obs = self.last_obs
        while self.t < until - 0.5 * self.dt:
            obs = self.step()
            if obs.plant_dead:
                break
        return obs

    # ------------------------------------------------------------ steady state

    def initialize_steady_state(self, load_mw: float) -> Observation:
        """Construct + polish a steady state at the commanded load [MW electric].

        Analytic back-calculation gives the initial guess; scipy.optimize.root
        on the derivative function (with loop-equilibrium conditions replacing
        the degenerate actuator rows) polishes it. Controllers are initialized
        bumpless at the solved outputs.
        """
        plant = self.plant
        cfg = self.cfg
        p0 = cfg["design"]["p_drum"]
        p_rated = cfg["design"]["p_rated"]
        load_w = load_mw * 1e6
        vf = cfg["loads"]["vital_fraction"]
        plant.loads.vital.p0 = vf * load_w
        plant.loads.nonvital.p0 = (1.0 - vf) * load_w
        self.control.load_ref = load_w

        tp = plant.turbine.tp
        rp = plant.turbine.rp
        omega0 = rp.omega0

        # --- analytic construction
        x_thr = tp.x_rated * load_w / p_rated
        m_turb = tp.k_t * x_thr * p0
        p_chest = x_thr * p0

        drum = plant.drum
        from hotwell import steam_properties as sp
        v_liq = drum.p.v_liq_nwl
        v_stm = drum.p.v_total - v_liq
        m_drum = v_liq / sp.v_f(p0) + v_stm / sp.v_g(p0)
        x_q = (v_stm / sp.v_g(p0)) / m_drum
        u_drum = m_drum * (sp.u_f(p0) + x_q * (sp.u_g(p0) - sp.u_f(p0)))

        da = plant.deaerator
        m_hw = plant.condenser.m_nominal(992.6)
        m_da = da.m_nominal()

        m_cond = m_turb  # exhaust = throttle flow at steady state
        p_cond = plant.condenser.p_cond(m_turb, 0.0)
        h_c = sp.hf_t(sp.tsat_lowp(p_cond))
        m_peg = da.m_pegging(m_cond, h_c, p0, sp.h_g(p0))
        m_fw = m_turb + m_peg
        q_fire = m_fw * (sp.h_g(p0) - da.h_fw)
        x_fir = q_fire / (plant.eta_comb * plant.q_fuel_max)

        y = self.plant.registry.initial_vector()
        reg = plant.registry
        y[reg.index("fw_valve.x")] = 0.6
        y[reg.index("throttle.x")] = x_thr
        y[reg.index("firing.x")] = x_fir
        y[reg.index("cp1.s")] = 1.0
        y[reg.index("cp2.s")] = 0.0
        y[reg.index("fp1.s")] = 1.0
        y[reg.index("fp2.s")] = 0.0
        y[reg.index("drum.M")] = m_drum
        y[reg.index("drum.U")] = u_drum
        y[reg.index("chest.p")] = p_chest
        y[reg.index("rotor.omega")] = omega0
        y[reg.index("hotwell.M")] = m_hw
        y[reg.index("da.M")] = m_da

        # --- scipy root polish: unknowns = 13 states + lcv_x
        i_fw = reg.index("fw_valve.x")
        i_thr = reg.index("throttle.x")
        i_fir = reg.index("firing.x")
        i_omega = reg.index("rotor.omega")
        pump_idx = [plant.pumps[n].i_s for n in PUMP_NAMES]
        # NOTE: hotwell.M's mass-balance row is linearly dependent with da.M's
        # at the solution (both pin the same condensate flow), so the hotwell
        # is pinned by LEVEL = nominal instead; dM_hw/dt = 0 then follows.
        slow_idx = [reg.index(k) for k in
                    ("drum.M", "drum.U", "chest.p", "rotor.omega", "da.M")]
        slow_scale = np.array([1.0, 1e6, 1e4, 1e-2, 1.0])
        disc = self.disc

        def residual(u: np.ndarray) -> np.ndarray:
            yy = u[:reg.n]
            lcv = u[reg.n]
            cmds = Commands(fw_cmd=yy[i_fw], throttle_cmd=yy[i_thr],
                            firing_cmd=yy[i_fir], lcv_x=lcv)
            ydot, aux = plant.deriv(yy, cmds, disc)
            r = np.empty(reg.n + 1)
            r[0:4] = ydot[pump_idx]
            r[4:9] = ydot[slow_idx] / slow_scale
            r[9] = aux.hw_level_rel / 1e-3
            r[10] = (aux.p_drum - p0) / 1e4
            r[11] = aux.drum_level / 1e-3
            r[12] = aux.da_level_rel / 1e-3
            r[13] = (yy[i_omega] - omega0) / 1e-3
            return r

        # 14 unknowns (13 states + lcv_x) / 14 residuals: the three actuator
        # derivative rows are degenerate (cmd := position) and are replaced by
        # the loop-equilibrium conditions r[9..13].
        u0 = np.concatenate([y, [0.6]])
        sol = root(residual, u0, method="hybr", options={"xtol": 1e-13})
        if not sol.success:
            raise RuntimeError(f"steady-state root failed: {sol.message}")
        self.y = sol.x[:reg.n].copy()
        lcv_x = float(sol.x[reg.n])

        # --- controllers bumpless at solved outputs
        self.t = 0.0
        cmds = Commands(fw_cmd=float(self.y[i_fw]),
                        throttle_cmd=float(self.y[i_thr]),
                        firing_cmd=float(self.y[i_fir]), lcv_x=lcv_x)
        self.commands = cmds
        _, aux = plant.deriv(self.y, cmds, disc)
        self.control.drum_level.initialize(cmds.fw_cmd, aux.drum_level)
        self.control.drum_pressure.initialize(cmds.firing_cmd, aux.p_drum)
        self.control.da_level.initialize(lcv_x, aux.da_level_rel)

        obs = self._observe(aux)
        self.last_obs = obs
        self.last_aux = aux
        self.audit_acc.reset(self.t, plant.total_water_mass(self.y, aux))
        return obs

    def steady_state_residual_norm(self) -> float:
        """Max |scaled derivative| at the current state (T2 check)."""
        ydot, _ = self.plant.deriv(self.y, self.commands, self.disc)
        spans = self.plant.registry.spans()
        return float(np.max(np.abs(ydot) / spans))

    def audit(self) -> AuditReport:
        """Mass/energy closure report at the current state."""
        aux = self.last_aux
        assert aux is not None
        return self.audit_acc.report(
            self.t, self.plant.total_water_mass(self.y, aux),
            aux.q_fire, aux.p_elec, aux.q_cond_duty, aux.p_damping)
