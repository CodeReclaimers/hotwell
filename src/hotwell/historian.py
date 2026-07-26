"""Historian: preallocated ring buffers with a query/export API.

Full-rate (20 Hz) trailing window plus 1 Hz decimated storage for the whole
run. This module is the future strip-chart feed and agent historian tool —
it must stay free of simulator imports.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


class Historian:
    """Records a fixed signal list every step; ring buffer + decimated store."""

    def __init__(self, signals: list[str], dt: float,
                 fine_window: float = 600.0, coarse_period: float = 1.0) -> None:
        self.signals = list(signals)
        self._idx = {s: i for i, s in enumerate(self.signals)}
        self.dt = dt
        m = len(self.signals)
        self._n_fine = int(round(fine_window / dt))
        self._fine = np.full((self._n_fine, m), np.nan)
        self._fine_t = np.full(self._n_fine, np.nan)
        self._fine_ptr = 0
        self._fine_count = 0
        self._stride = max(1, int(round(coarse_period / dt)))
        self._coarse: list[np.ndarray] = []
        self._coarse_t: list[float] = []
        self._step = 0

    def record(self, t: float, values: dict[str, float]) -> None:
        """Store one step's samples (missing signals record as NaN)."""
        row = np.array([values.get(s, np.nan) for s in self.signals])
        self._fine[self._fine_ptr] = row
        self._fine_t[self._fine_ptr] = t
        self._fine_ptr = (self._fine_ptr + 1) % self._n_fine
        self._fine_count = min(self._fine_count + 1, self._n_fine)
        if self._step % self._stride == 0:
            self._coarse.append(row)
            self._coarse_t.append(t)
        self._step += 1

    # ------------------------------------------------------------------ query

    def _fine_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if self._fine_count < self._n_fine:
            sl = slice(0, self._fine_count)
            return self._fine_t[sl], self._fine[sl]
        order = np.concatenate([np.arange(self._fine_ptr, self._n_fine),
                                np.arange(0, self._fine_ptr)])
        return self._fine_t[order], self._fine[order]

    def query(self, signals: list[str], t0: float, t1: float,
              max_points: int = 2000) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Samples in [t0, t1]: full rate where the fine window covers the
        range, 1 Hz elsewhere; decimated by stride to <= max_points."""
        ft, fv = self._fine_arrays()
        fine_start = ft[0] if len(ft) else np.inf
        parts_t: list[np.ndarray] = []
        parts_v: list[np.ndarray] = []
        if t0 < fine_start and self._coarse:
            ct = np.array(self._coarse_t)
            cv = np.stack(self._coarse)
            m = (ct >= t0) & (ct <= t1) & (ct < fine_start)
            parts_t.append(ct[m])
            parts_v.append(cv[m])
        if len(ft):
            m = (ft >= t0) & (ft <= t1)
            parts_t.append(ft[m])
            parts_v.append(fv[m])
        t = np.concatenate(parts_t) if parts_t else np.empty(0)
        v = np.concatenate(parts_v) if parts_v else np.empty((0, len(self.signals)))
        if len(t) > max_points:
            stride = int(np.ceil(len(t) / max_points))
            t = t[::stride]
            v = v[::stride]
        return t, {s: v[:, self._idx[s]] for s in signals}

    # ----------------------------------------------------------------- export

    def export_npz(self, path: str | Path) -> None:
        t, vals = self.query(self.signals, -np.inf, np.inf, max_points=10 ** 9)
        np.savez(path, t=t, **{s: vals[s] for s in self.signals})

    def export_csv(self, path: str | Path, signals: list[str] | None = None) -> None:
        signals = signals or self.signals
        t, vals = self.query(signals, -np.inf, np.inf, max_points=10 ** 9)
        data = np.column_stack([t] + [vals[s] for s in signals])
        header = ",".join(["t"] + signals)
        np.savetxt(path, data, delimiter=",", header=header, comments="")
