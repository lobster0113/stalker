"""95% Wilson score interval for a binomial proportion, shared by the CI summaries (#819).

`phh_stats` reports it in percent (one decimal), `web_hit_rate` as a 0..1 fraction (six decimals); both round
the raw `wilson95` here so the formula lives in one place.
"""
from __future__ import annotations

import math

Z95 = 1.959964


def wilson95(hits: int, n: int) -> tuple[float, float] | None:
    """(lo, hi) as fractions 0..1, unrounded; None when n == 0. Stays inside [0, 1] at 0/n and n/n."""
    if not n:
        return None
    z2 = Z95 * Z95
    p = hits / n
    d = 1 + z2 / n
    mid = (p + z2 / (2 * n)) / d
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d
    return max(0.0, mid - half), min(1.0, mid + half)
