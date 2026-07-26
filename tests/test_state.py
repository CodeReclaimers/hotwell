"""State registry: named slots, stable indices, initial vector, spans."""
import numpy as np
import pytest

from hotwell.state import StateRegistry


def test_register_and_build():
    reg = StateRegistry()
    i_m = reg.register("drum.M", 10.7e3, "kg", 5e3)
    i_u = reg.register("drum.U", 1.47e10, "J", 5e9)
    i_x = reg.register("fw_valve.x", 0.6, "-", 1.0)
    assert (i_m, i_u, i_x) == (0, 1, 2)
    assert reg.n == 3
    assert reg.index("drum.U") == 1
    y = reg.initial_vector()
    assert y.dtype == np.float64
    np.testing.assert_allclose(y, [10.7e3, 1.47e10, 0.6])
    np.testing.assert_allclose(reg.spans(), [5e3, 5e9, 1.0])
    assert reg.names() == ["drum.M", "drum.U", "fw_valve.x"]
    d = reg.as_dict(y)
    assert d["fw_valve.x"] == 0.6


def test_duplicate_name_rejected():
    reg = StateRegistry()
    reg.register("rotor.omega", 376.99, "rad/s", 40.0)
    with pytest.raises(ValueError, match="duplicate"):
        reg.register("rotor.omega", 0.0, "rad/s", 1.0)


def test_nonpositive_span_rejected():
    reg = StateRegistry()
    with pytest.raises(ValueError, match="span"):
        reg.register("chest.p", 6.8e6, "Pa", 0.0)
