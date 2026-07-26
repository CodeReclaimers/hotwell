"""0.2.0 package-data migration: hotwell runs with no repo checkout present.

The gate that matters is *where the data lives*, not merely "does it load from
another directory". Under an editable install the old repo-relative constants
(`Path(__file__).parents[3] / "data"`) still resolve into the checkout, so a
plain chdir-to-tmpdir test passes against the pre-migration code and proves
nothing. These tests therefore assert every default resource is located inside
the installed package directory, which the old paths cannot satisfy.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import hotwell
from hotwell import data
from hotwell.plant import load_config
from hotwell.protection.tables import load_protection_table
from hotwell.scenario import load_scenario
from hotwell.simulator import Simulator

PKG_ROOT = Path(hotwell.__file__).resolve().parent


def _inside_package(resource) -> bool:
    return Path(str(resource)).resolve().is_relative_to(PKG_ROOT)


def test_default_resources_live_inside_the_package():
    """The discriminating check: repo-relative paths would fail this."""
    assert _inside_package(data.baseline_config_path()), \
        f"baseline config outside {PKG_ROOT}"
    assert _inside_package(data.protection_table_path()), \
        f"protection table outside {PKG_ROOT}"
    scenarios = data.builtin_scenarios()
    assert set(scenarios) == {"load_step", "cp1_trip_recovered",
                              "cp1_trip_unrecovered"}
    for name, path in scenarios.items():
        assert _inside_package(path), f"scenario {name} outside {PKG_ROOT}"


def test_loaders_work_from_a_directory_with_no_checkout(tmp_path):
    """Every default loader works with cwd outside the repo entirely."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert not (tmp_path / "configs").exists()
        cfg = load_config()
        assert cfg["design"]["p_drum"] == pytest.approx(8.0e6)
        table = load_protection_table()
        assert len(table.conditions) == 19
        sc = load_scenario(data.builtin_scenarios()["cp1_trip_recovered"])
        assert sc.name == "cp1_trip_recovered"
        assert sc.seed == 42
    finally:
        os.chdir(cwd)


def test_canonical_scenario_runs_from_a_bare_directory(tmp_path):
    """A short canonical run with no repo-relative anything in reach."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        sim = Simulator.from_scenario(
            data.builtin_scenarios()["cp1_trip_unrecovered"])
        sim.run(310.0)
        # CP-1 tripped at t=300 s per the scenario; the indication is honest.
        assert sim.last_obs.indications["cp1_tripped"] is True
        assert sim.t == pytest.approx(310.0, abs=0.05)
        print(f"\n  ran to t={sim.t:.2f} s from {tmp_path}; "
              f"first-out={sim.engine.first_out}")
    finally:
        os.chdir(cwd)


def test_path_overrides_still_accepted(tmp_path):
    """Explicit user-supplied paths keep working (§11.3 requirement)."""
    custom = tmp_path / "custom.yaml"
    custom.write_text(data.read_text(data.protection_table_path()))
    table = load_protection_table(custom)
    assert len(table.conditions) == 19
    # str and Path both accepted
    assert len(load_protection_table(str(custom)).conditions) == 19
