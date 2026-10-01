"""Closed-interval arithmetic on the time axis (minutes relative to scenario reference)."""

from __future__ import annotations

import numpy as np

INF = float("inf")
Interval = tuple[float, float]


def merge(ivs: list[Interval]) -> list[Interval]:
    ivs = sorted((a, b) for a, b in ivs if b > a)
    out: list[list[float]] = []
    for a, b in ivs:
        if out and a <= out[-1][1] + 1e-9:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def subtract(ivs: list[Interval], cut: Interval) -> list[Interval]:
    ca, cb = cut
    out: list[Interval] = []
    for a, b in ivs:
        if b <= ca or a >= cb:
            out.append((a, b))
            continue
        if a < ca:
            out.append((a, ca))
        if b > cb:
            out.append((cb, b))
    return out


def contains(ivs: list[Interval], t: float) -> bool:
    return any(a <= t < b for a, b in ivs)


def first_overlap(ivs: list[Interval], a: float, b: float) -> Interval | None:
    for x, y in ivs:
        if x < b and y > a:
            return (x, y)
    return None


def next_start_after(ivs: list[Interval], t: float) -> float:
    """Start of the interval active at ``t`` (returns ``t``) or of the next one; INF if none."""
    for x, y in ivs:
        if x <= t < y:
            return t
        if x > t:
            return x
    return INF


def threshold_intervals(t: np.ndarray, d: np.ndarray, thr: float) -> list[Interval]:
    """Intervals where the series ``d`` is ≥ ``thr``; crossings linearly interpolated.

    An exceedance at the first sample extends to -INF (already exceeded), at the last sample to +INF.
    """
    above = d >= thr
    if not above.any():
        return []
    out: list[Interval] = []
    n = len(t)
    i = 0
    while i < n:
        if not above[i]:
            i += 1
            continue
        if i == 0:
            start = -INF
        else:
            d0, d1 = d[i - 1], d[i]
            ok = np.isfinite(d0) and np.isfinite(d1) and d1 != d0
            start = float(t[i - 1] + (thr - d0) / (d1 - d0) * (t[i] - t[i - 1])) if ok else float(t[i])
        j = i
        while j < n and above[j]:
            j += 1
        if j >= n:
            end = INF
        else:
            d0, d1 = d[j - 1], d[j]
            ok = np.isfinite(d0) and np.isfinite(d1) and d0 != d1
            end = float(t[j - 1] + (d0 - thr) / (d0 - d1) * (t[j] - t[j - 1])) if ok else float(t[j])
        out.append((start, end))
        i = j
    return out


def finite_or_none(x: float) -> float | None:
    return None if x is None or x != x or x in (INF, -INF) else float(x)
