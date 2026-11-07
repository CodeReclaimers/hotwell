"""0.2.0 §11.2: optional annunciator legends on protection-table entries.

Pure display data — the protection engine never reads `label`. The panel's
annunciator windows are engraved two-line legends, so the parser enforces
1-2 lines of <= 12 characters and falls back to the bare id.
"""
from __future__ import annotations

import pytest

from hotwell.protection.tables import (
    LABEL_MAX_CHARS,
    LABEL_MAX_LINES,
    load_protection_table,
)

MINIMAL = """
conditions:
  - {{id: TEST_COND, signal: drum_level, op: lt, setpoint: -0.1, delay: 1.0,
     latching: false, actions: [alarm]{extra}}}
"""


def write_table(tmp_path, extra=""):
    p = tmp_path / "t.yaml"
    p.write_text(MINIMAL.format(extra=extra))
    return p


def test_every_shipped_condition_has_a_legend_that_fits_a_window():
    table = load_protection_table()
    assert len(table.conditions) == 22  # 19 in 0.3.0 + COND_P_HIHI (M2) + CP1/CP2_SUCTION (M5b)
    for c in table.conditions:
        assert c.label, f"{c.id} has no label"
        assert 1 <= len(c.label) <= LABEL_MAX_LINES
        for line in c.label:
            assert len(line) <= LABEL_MAX_CHARS, (c.id, line, len(line))
    widest = max((len(ln), c.id, ln)
                 for c in table.conditions for ln in c.label)
    print(f"\n  {len(table.conditions)} legends, widest line {widest[0]} chars: "
          f"{widest[1]} {widest[2]!r}")


def test_legend_defaults_to_the_id_when_absent(tmp_path):
    table = load_protection_table(write_table(tmp_path))
    c = table.conditions[0]
    assert c.label == ()          # nothing stored
    assert c.legend == ("TEST_COND",)  # but the display accessor is populated


def test_explicit_legend_is_parsed(tmp_path):
    table = load_protection_table(
        write_table(tmp_path, ', label: ["DRUM LEVEL", "LOW"]'))
    assert table.conditions[0].label == ("DRUM LEVEL", "LOW")
    assert table.conditions[0].legend == ("DRUM LEVEL", "LOW")


def test_overlong_line_is_rejected(tmp_path):
    too_long = "THIRTEEN CHRS"
    assert len(too_long) == 13  # guard the fixture itself
    with pytest.raises(ValueError, match="13 chars"):
        load_protection_table(
            write_table(tmp_path, f', label: ["{too_long}", "X"]'))


def test_too_many_lines_rejected(tmp_path):
    with pytest.raises(ValueError, match="1-2 lines"):
        load_protection_table(
            write_table(tmp_path, ', label: ["A", "B", "C"]'))


def test_scalar_label_is_split_on_newlines(tmp_path):
    table = load_protection_table(
        write_table(tmp_path, ', label: "DRUM LEVEL\\nLOW"'))
    assert table.conditions[0].label == ("DRUM LEVEL", "LOW")


def test_labels_do_not_affect_engine_behavior():
    """A label change must never move a setpoint or an action."""
    table = load_protection_table()
    lolo = table.by_id("DRUM_LVL_LOLO")
    assert lolo.setpoint == pytest.approx(-0.300)
    assert lolo.actions == ("mft", "turbine_trip")
    assert lolo.latching is True
    assert lolo.is_trip is True
