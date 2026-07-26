#!/usr/bin/env python3
"""Print the steady-state balance sheet at a commanded load (default 60 MW).

Usage: python scripts/steady_state.py [load_mw]
"""
from __future__ import annotations

import sys

from hotwell.simulator import Simulator


def main() -> None:
    load_mw = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    sim = Simulator(seed=0)
    sim.initialize_steady_state(load_mw)
    aux = sim.last_aux
    y = sim.y
    reg = sim.plant.registry
    assert aux is not None

    print(f"=== hotwell steady state @ {load_mw:.1f} MW ===")
    print(f"residual norm (scaled |ydot|_max): {sim.steady_state_residual_norm():.3e} 1/s")
    print()
    print("-- flows [kg/s] --")
    print(f"steam (throttle):   {aux.m_throttle:8.3f}")
    print(f"pegging steam:      {aux.m_peg:8.3f}")
    print(f"feedwater:          {aux.m_fw:8.3f}")
    print(f"condensate:         {aux.m_cond:8.3f}")
    print(f"exhaust:            {aux.m_exhaust:8.3f}")
    print()
    print("-- pressures / levels --")
    print(f"drum pressure:      {aux.p_drum / 1e6:8.4f} MPa")
    print(f"chest pressure:     {y[reg.index('chest.p')] / 1e6:8.4f} MPa")
    print(f"condenser pressure: {aux.p_cond / 1e3:8.3f} kPa")
    print(f"drum level:         {aux.drum_level * 1e3:8.2f} mm")
    print(f"hotwell level rel:  {aux.hw_level_rel * 1e3:8.2f} mm")
    print(f"DA level rel:       {aux.da_level_rel * 1e3:8.2f} mm")
    print()
    print("-- powers [MW] --")
    print(f"firing (effective): {aux.q_fire / 1e6:8.3f}")
    print(f"mechanical:         {aux.p_mech / 1e6:8.3f}")
    print(f"electrical:         {aux.p_elec / 1e6:8.3f}")
    print(f"condenser duty:     {aux.q_cond_duty / 1e6:8.3f}")
    print(f"damping loss:       {aux.p_damping / 1e6:8.5f}")
    rep = sim.audit()
    print(f"energy closure:     {rep.energy_residual_frac * 100:8.4f} % of firing")
    print()
    print("-- actuators / pumps --")
    print(f"fw valve:  {y[reg.index('fw_valve.x')]:.4f}   throttle: "
          f"{y[reg.index('throttle.x')]:.4f}   firing: {y[reg.index('firing.x')]:.4f}"
          f"   DA LCV: {sim.commands.lcv_x:.4f}")
    print(f"NPSH margins: FP1 {aux.feed_flow.margin[0]:.2f} m, "
          f"CP1 {aux.cond_flow.margin[0]:.2f} m")
    print(f"total water inventory: {rep.mass_total / 1e3:.2f} t")


if __name__ == "__main__":
    main()
