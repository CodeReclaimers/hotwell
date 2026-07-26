"""Step loop: RK4 integration, strict step sequencing, events, steady-state init.

Step sequence (plan section 3.2, strict order):
  1. apply scenario events + submitted actions (validated; invalid recorded)
  2. controllers (previous step's sensed obs)  3. RK4 with discrete+commands
  frozen  4. event layer (protection on this step's sensed values)  5. sensors
  6. historian/audit.  Internally the sensing pipeline runs once, immediately
  before the event layer, so protection consumes sensed values (HANDOFF D11).

Determinism: one numpy.random.Generator owned here (no stochastic elements
are active in phase 1, but all future randomness must flow from it); a
per-step SHA-256 over the state vector provides the T5 trajectory hash.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.optimize import root

from hotwell.actions import check_schema
from hotwell.audit import AuditAccumulator, AuditReport
from hotwell.components.pumps import (
    MODE_RUNNING,
    MODE_STARTING,
    MODE_STOPPED,
    MODE_TRIPPED,
)
from hotwell.control.loops import Commands, ControlSystem, GovernorParams
from hotwell.control.pid import PIParams
from hotwell.historian import Historian
from hotwell.plant import PUMP_NAMES, Aux, Discrete, Plant, load_config
from hotwell.protection.interlocks import FiredAction, ProtectionEngine
from hotwell.protection.tables import load_protection_table
from hotwell.scenario import Scenario, load_scenario
from hotwell.sensors import Observation, RejectedAction, SensorBank, SensorFault

DT = 0.05  # s — fixed step, locked decision
TWO_PI = 6.283185307179586

_MODE_CODE = {MODE_STOPPED: 0.0, MODE_STARTING: 0.5, MODE_RUNNING: 1.0,
              MODE_TRIPPED: -1.0}


def _pi_params(d: dict) -> PIParams:
    return PIParams(kp=d["kp"], ki=d["ki"], lo=d["lo"], hi=d["hi"],
                    t_track=d["t_track"])


class Simulator:
    """Owns plant, controllers, protection, discrete state, sensors, audit,
    historian, scenario, and the clock."""

    def __init__(self, config: dict | str | Path | None = None,
                 scenario: Scenario | None = None,
                 seed: int | None = None,
                 protection_path: str | Path | None = None) -> None:
        cfg = config if isinstance(config, dict) else load_config(config)
        self.cfg = cfg
        self.plant = Plant(cfg)
        if seed is None:
            seed = scenario.seed if scenario is not None else 0
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.dt = DT
        self.t = 0.0
        self.y = self.plant.registry.initial_vector()
        self.disc = Discrete()
        self.sensors = SensorBank()
        self.audit_acc = AuditAccumulator()
        self.engine = ProtectionEngine(load_protection_table(protection_path))
        self.scenario = scenario
        self._event_idx = 0
        self.rejected: list[RejectedAction] = []
        self.historian: Historian | None = None
        self._hash = hashlib.sha256()

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

    @classmethod
    def from_scenario(cls, scenario_path: str | Path,
                      config: dict | str | Path | None = None) -> Simulator:
        sc = load_scenario(scenario_path)
        sim = cls(config, scenario=sc)
        sim.initialize_steady_state(sc.load_mw)
        return sim

    # ------------------------------------------------------------- actions

    def _reject(self, key: str, value, reason: str) -> None:
        self.rejected.append(RejectedAction(self.t, {key: value}, reason))

    def apply_actions(self, actions: dict) -> None:
        """Validate and apply an action dict (invalid entries recorded)."""
        for key, value in actions.items():
            reason = check_schema(key, value)
            if reason is not None:
                self._reject(key, value, reason)
                continue
            self._apply_one(key, value)

    def _apply_one(self, key: str, value) -> None:
        disc = self.disc
        ctl = self.control
        if key.endswith(".start") or key.endswith(".stop"):
            pump, verb = key.split(".")
            mode = disc.pump_modes[pump]
            if verb == "start":
                if mode != MODE_STOPPED:
                    self._reject(key, value, f"{pump} is {mode}, not stopped")
                elif pump in disc.start_inhibited:
                    self._reject(key, value, f"{pump} start inhibited")
                elif not disc.breaker_closed:
                    self._reject(key, value, "bus deenergized")
                elif value:
                    disc.pump_modes[pump] = MODE_STARTING
            else:
                if mode not in (MODE_STARTING, MODE_RUNNING):
                    self._reject(key, value, f"{pump} is {mode}, not running")
                elif value:
                    disc.pump_modes[pump] = MODE_STOPPED
        elif key == "governor.load_ref_mw":
            ctl.load_ref = float(value) * 1e6
        elif key == "loads.nonvital.connect":
            if not disc.breaker_closed:
                self._reject(key, value, "bus deenergized")
            else:
                disc.nonvital_connected = bool(value)
        elif key.startswith("loop."):
            ctl.loop(key.split(".")[1]).mode = value
        elif key == "fw_valve.manual_cmd":
            self._manual_cmd("drum_level", key, value)
        elif key == "firing.manual_cmd":
            if disc.mft:
                self._reject(key, value, "MFT latched")
            else:
                self._manual_cmd("drum_pressure", key, value)
        elif key == "da_lcv.manual_cmd":
            self._manual_cmd("da_level", key, value)
        elif key == "alarm.ack":
            if not self.engine.acknowledge(value):
                self._reject(key, value, f"no active alarm {value!r}")
        elif key == "trips.reset":
            if value:
                self._do_reset()

    def _manual_cmd(self, loop: str, key: str, value: float) -> None:
        pi = self.control.loop(loop)
        if pi.mode != "manual":
            self._reject(key, value, f"{loop} loop in auto")
        else:
            pi.manual_cmd = float(value)

    def _do_reset(self) -> None:
        assert self.last_obs is not None
        self.engine.reset(self.t, self.last_obs.values)
        latched = [c for c in self.engine.table.conditions
                   if self.engine.states[c.id].latched]
        self.disc.mft = any("mft" in c.actions for c in latched)
        self.disc.turbine_trip = any("turbine_trip" in c.actions for c in latched)
        if not self.disc.turbine_trip:
            self.disc.breaker_closed = True
        for p in PUMP_NAMES:
            still = any(c.target == p and "trip_pump" in c.actions for c in latched)
            if self.disc.pump_modes[p] == MODE_TRIPPED and not still:
                self.disc.pump_modes[p] = MODE_STOPPED

    # ------------------------------------------------------- scenario events

    def _apply_scenario_events(self) -> None:
        sc = self.scenario
        if sc is None:
            return
        while self._event_idx < len(sc.events) and \
                sc.events[self._event_idx].t <= self.t + 1e-9:
            ev = sc.events[self._event_idx]
            self._event_idx += 1
            p = ev.params
            if ev.type == "trip_pump":
                self._trip_pump(p["target"], p.get("reason", "scenario"))
            elif ev.type == "inhibit_start":
                self.disc.start_inhibited.add(p["target"])
            elif ev.type == "sensor_fault":
                self.sensors.faults[p["target"]] = SensorFault(
                    kind=p["kind"], bias=float(p.get("bias", 0.0)),
                    t_start=ev.t, t_end=float(p.get("t_end", np.inf)))
            elif ev.type == "set_air_ingress":
                self.disc.air_ingress = float(p["value"])
            elif ev.type == "set_load":
                block = getattr(self.plant.loads, p["target"])
                block.p0 = float(p["p0"])
            elif ev.type == "action":
                self.apply_actions(p["command"])

    def _trip_pump(self, pump: str, reason: str) -> None:
        if self.disc.pump_modes[pump] in (MODE_STARTING, MODE_RUNNING):
            self.disc.pump_modes[pump] = MODE_TRIPPED
            self.disc.pump_trip_reason[pump] = reason
            self.engine.record_external_trip(self.t, f"{pump.upper()}_TRIP:{reason}")

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

    def _apply_protective_actions(self, fired: list[FiredAction]) -> None:
        disc = self.disc
        y = self.y
        for fa in fired:
            if fa.action == "mft" and not disc.mft:
                disc.mft = True
                y[self.plant.firing.i_x] = 0.0  # fuel trip valve slams
            elif fa.action == "turbine_trip" and not disc.turbine_trip:
                disc.turbine_trip = True
                y[self.plant.throttle.i_x] = 0.0  # throttle slams
                disc.breaker_closed = False       # generator breaker opens
                for p in PUMP_NAMES:              # bus dead -> motor contactors drop
                    self._trip_pump(p, "bus_dead")
            elif fa.action == "trip_pump" and fa.target is not None:
                self._trip_pump(fa.target, fa.condition_id)
            elif fa.action == "shed_nonvital":
                disc.nonvital_connected = False
            elif fa.action == "safety_valve":
                disc.safety_open = fa.value

    def _event_layer(self, aux: Aux) -> None:
        """Discrete-state updates at the step boundary: position clamps, pump
        start completion, plant-dead. (Safety-valve hysteresis and trips come
        through the protection engine.)"""
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
        all_pumps_stopped = all(
            self.disc.pump_modes[n] in (MODE_STOPPED, MODE_TRIPPED)
            for n in PUMP_NAMES)
        if self.disc.mft and all_pumps_stopped:
            self.disc.plant_dead = True

    def _sample(self, aux: Aux) -> dict[str, float]:
        truth = self.plant.truth(self.t, self.y, aux, self.disc)
        truth["da_lcv_pos"] = self.commands.lcv_x
        return self.sensors.sample(self.t, truth)

    def _indications(self) -> dict[str, bool | str]:
        d: dict[str, bool | str] = {}
        for n in PUMP_NAMES:
            d[f"{n}_running"] = self.disc.pump_modes[n] == MODE_RUNNING
            d[f"{n}_tripped"] = self.disc.pump_modes[n] == MODE_TRIPPED
        d.update({
            "mft": self.disc.mft,
            "turbine_trip": self.disc.turbine_trip,
            "safety_valve_open": self.disc.safety_open,
            "nonvital_connected": self.disc.nonvital_connected,
            "breaker_closed": self.disc.breaker_closed,
        })
        return d

    def _historian_signals(self) -> list[str]:
        extra = ["m_peg", "m_relief", "q_fire", "p_mech", "mft", "turbine_trip",
                 "safety_open", "nonvital_connected", "breaker_closed",
                 "plant_dead", "alarm_count"]
        extra += [f"{n}_mode" for n in PUMP_NAMES]
        return list(self.sensors.spec.keys()) + extra

    def _record(self, aux: Aux, sensed: dict[str, float]) -> None:
        if self.historian is None:
            return
        row = dict(sensed)
        disc = self.disc
        row.update({
            "m_peg": aux.m_peg, "m_relief": aux.m_relief,
            "q_fire": aux.q_fire, "p_mech": aux.p_mech,
            "mft": float(disc.mft), "turbine_trip": float(disc.turbine_trip),
            "safety_open": float(disc.safety_open),
            "nonvital_connected": float(disc.nonvital_connected),
            "breaker_closed": float(disc.breaker_closed),
            "plant_dead": float(disc.plant_dead),
            "alarm_count": float(len(self.engine.alarm_states())),
        })
        for n in PUMP_NAMES:
            row[f"{n}_mode"] = _MODE_CODE[disc.pump_modes[n]]
        self.historian.record(self.t, row)

    def step(self, actions: dict | None = None) -> Observation:
        """Advance one step (plan section 3.2 order); returns the observation."""
        assert self.last_obs is not None, "call initialize_steady_state first"
        # 1. scenario events + submitted actions
        self._apply_scenario_events()
        if actions:
            self.apply_actions(actions)
        # 2. controllers on previous sensed observation
        cmds = self.control.update(self.last_obs.values, self.dt)
        if self.disc.mft:
            cmds = replace(cmds, firing_cmd=0.0)
        if self.disc.turbine_trip:
            cmds = replace(cmds, throttle_cmd=0.0)
        self.commands = cmds
        # 3. integrate
        y_new, aux = self._rk4()
        self.y = y_new
        self.t += self.dt
        # 4. event layer — protection acts on this step's sensed values (D11)
        sensed = self._sample(aux)
        fired = self.engine.evaluate(self.t, sensed)
        self._apply_protective_actions(fired)
        self._event_layer(aux)
        # 5. observation
        obs = Observation(t=self.t, values=sensed,
                          alarms=self.engine.alarm_states(),
                          indications=self._indications(),
                          plant_dead=self.disc.plant_dead)
        # 6. historian + audit + trajectory hash
        self._record(aux, sensed)
        self.audit_acc.accumulate(aux.m_relief, self.dt)
        self._hash.update(self.y.tobytes())
        self.last_obs = obs
        self.last_aux = aux
        return obs

    def run(self, until: float | None = None) -> Observation:
        """Step until `until` [s] (default: scenario max_t) or plant death."""
        if until is None:
            assert self.scenario is not None
            until = self.scenario.max_t
        obs = self.last_obs
        while self.t < until - 0.5 * self.dt:
            obs = self.step()
            if obs.plant_dead:
                break
        return obs

    @property
    def state_history_hash(self) -> str:
        """SHA-256 over every post-step state vector so far (T5)."""
        return self._hash.hexdigest()

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
        vf_frac = cfg["loads"]["vital_fraction"]
        plant.loads.vital.p0 = vf_frac * load_w
        plant.loads.nonvital.p0 = (1.0 - vf_frac) * load_w
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

        sensed = self._sample(aux)
        obs = Observation(t=self.t, values=sensed, alarms=[],
                          indications=self._indications(), plant_dead=False)
        self.last_obs = obs
        self.last_aux = aux
        self.audit_acc.reset(self.t, plant.total_water_mass(self.y, aux))
        self.historian = Historian(self._historian_signals(), self.dt)
        self._record(aux, sensed)
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
