"""0.4.0 M1 — named rng streams (plan invariant I2)."""
import numpy as np
import pytest

from hotwell.plant import load_config
from hotwell.rng import STREAM_IDS, StreamBank
from hotwell.sensors import OBSERVATION_SPEC
from hotwell.simulator import Simulator

# Append-only pin. Adding entries to STREAM_IDS is fine; changing or removing
# any line below breaks every recorded run that used that stream.
PINNED_IDS = {
    "sensor.drum_pressure": 1000, "sensor.drum_level": 1001,
    "sensor.steam_flow": 1002, "sensor.feed_flow": 1003,
    "sensor.condensate_flow": 1004, "sensor.chest_pressure": 1005,
    "sensor.cond_pressure": 1006, "sensor.hotwell_level": 1007,
    "sensor.da_level": 1008, "sensor.da_pressure": 1009,
    "sensor.frequency": 1010, "sensor.mw_out": 1011,
    "sensor.cp1_current": 1012, "sensor.cp2_current": 1013,
    "sensor.fp1_current": 1014, "sensor.fp2_current": 1015,
    "sensor.fw_valve_pos": 1016, "sensor.throttle_pos": 1017,
    "sensor.firing_rate": 1018, "sensor.da_lcv_pos": 1019,
    "sensor.fp1_npsh_margin": 1020, "sensor.fp2_npsh_margin": 1021,
    "sensor.makeup_flow": 1022, "sensor.makeup_valve_pos": 1023,   # M5b
    "sensor.cp1_npsh_margin": 1024, "sensor.cp2_npsh_margin": 1025,
    "load.vital": 2000, "load.nonvital": 2001,
    "operator": 3000,
}


def test_stream_ids_are_append_only():
    changed = {k: (v, STREAM_IDS.get(k)) for k, v in PINNED_IDS.items()
               if STREAM_IDS.get(k) != v}
    added = sorted(set(STREAM_IDS) - set(PINNED_IDS))
    print(f"\n{len(STREAM_IDS)} streams; pinned {len(PINNED_IDS)}; "
          f"added since pin: {added}; changed/removed: {changed}")
    assert not changed


def test_stream_ids_unique_and_single_word():
    """Distinct IDs, each < 2^32, so the SeedSequence entropy
    words(seed) + [id] is injective in (seed, id)."""
    ids = list(STREAM_IDS.values())
    assert len(ids) == len(set(ids))
    assert all(0 <= i < 2**32 for i in ids)


def test_every_instrument_has_a_sensor_stream():
    """Coverage: a new instrument (e.g. M5b makeup_flow) fails here until its
    stream is registered."""
    missing = [s.name for s in OBSERVATION_SPEC
               if f"sensor.{s.name}" not in STREAM_IDS]
    print(f"\ninstruments without a stream: {missing}")
    assert not missing


def test_same_seed_same_draws_different_seed_different_draws():
    a = StreamBank(42).stream("sensor.drum_level").normal(size=1000)
    b = StreamBank(42).stream("sensor.drum_level").normal(size=1000)
    c = StreamBank(43).stream("sensor.drum_level").normal(size=1000)
    print(f"\nseed 42 vs 42 max |diff| {np.max(np.abs(a - b))}; "
          f"seed 42 vs 43 corr {np.corrcoef(a, c)[0, 1]:+.4f}")
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_consuming_one_stream_does_not_shift_another():
    fresh = StreamBank(7).stream("sensor.feed_flow").normal(size=500)
    bank = StreamBank(7)
    bank.stream("sensor.drum_level").normal(size=12345)   # heavy use of A
    bank.stream("load.nonvital").normal(size=3)
    interleaved = []
    for _ in range(500):                                  # interleave A and B
        bank.stream("sensor.drum_level").normal()
        interleaved.append(bank.stream("sensor.feed_flow").normal())
    print(f"\nfeed_flow stream: fresh vs after 12345+500 draws on drum_level, "
          f"max |diff| {np.max(np.abs(fresh - np.array(interleaved)))}")
    assert np.array_equal(fresh, np.array(interleaved))


def test_streams_are_mutually_uncorrelated():
    """Weak sanity bound on cross-stream independence: |corr| over 10^5 draws
    for every adjacent-ID pair stays below 5 sigma (5/sqrt(n) = 0.0158)."""
    n = 100_000
    bank = StreamBank(42)
    names = sorted(STREAM_IDS, key=STREAM_IDS.get)
    draws = {k: bank.stream(k).normal(size=n) for k in names}
    worst = max(abs(np.corrcoef(draws[a], draws[b])[0, 1])
                for a, b in zip(names, names[1:], strict=False))
    print(f"\nworst adjacent-ID |corr| over {n} draws: {worst:.5f} (bound 0.0158)")
    assert worst < 5.0 / np.sqrt(n)


def test_stream_object_is_cached():
    bank = StreamBank(1)
    assert bank.stream("operator") is bank.stream("operator")


def test_unknown_stream_and_negative_seed_raise():
    with pytest.raises(KeyError, match="unknown rng stream"):
        StreamBank(0).stream("sensor.no_such_instrument")
    with pytest.raises(ValueError, match="non-negative"):
        StreamBank(-1)


def test_pinned_raw_draws_numpy_version_gate():
    """Pinned under numpy 2.5.1. Raw PCG64 output pins SeedSequence + bit
    generator; normal() pins the distribution algorithm, which NumPy does NOT
    promise to keep stable across releases. If this fails after a numpy
    upgrade, every noisy recorded run has stopped reproducing: re-pin
    deliberately, or pin numpy."""
    raw = [int(x) for x in
           StreamBank(42).stream("sensor.drum_level").bit_generator.random_raw(3)]
    nrm = StreamBank(42).stream("sensor.drum_level").normal(size=3).tolist()
    print(f"\nnumpy {np.__version__}: raw {raw}\nnormal {nrm}")
    assert raw == [2491596885235603570, 16407104577408639165, 14955272865311411715]
    assert nrm == [0.11610006701218922, 0.23067914034706685, 0.1631065687488972]


def test_simulator_owns_a_bank_seeded_from_the_run_seed():
    sim = Simulator(load_config(), seed=42)
    a = sim.streams.stream("operator").normal(size=4)
    b = StreamBank(42).stream("operator").normal(size=4)
    assert sim.streams.seed == 42
    assert np.array_equal(a, b)
