"""Simulated learner who answers a 5-step chip with error (#261, #216-1).

A person answering "how often do I win against what they do here?" (form A, `hand.equity`) or "what
share of hands is mine above?" (form B, `hand.pct`) does not report the true value. The learner sees
`x' = 0.5 + (1 - anchor) * (x - 0.5) + sigma * z` (z standard normal, clipped to [0, 1]): `anchor`
pulls the answer toward 0.5 (anchoring on "coin flip"), `sigma` is the random error. Both are
ASSUMPTIONS, one pair per level, not measurements — real input errors are #216-2's job.

The two forms differ in where the error lands. In form A the error is in equity units and the chip is
read against the quantile steps of the current spot's equity distribution, so the same error moves
the chip more where hands are bunched (dense equities after a dry flop). In form B the error is in
rank units (the position among all hands), so it moves the chip by the same amount everywhere.
Only a seeded `numpy.random.Generator` is used (no global randomness).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Level:
    sigma: float   # standard deviation of the random error, in the form's own unit
    anchor: float  # 0 = none, 1 = always answers 0.5


LEVELS = {
    "beginner": Level(0.15, 0.20),
    "mid": Level(0.08, 0.10),
    "expert": Level(0.04, 0.03),
    "exact": Level(0.0, 0.0),
}


def perceive(x: float, level: Level, rng: np.random.Generator) -> float:
    """The learner's noisy reading of a true value in [0, 1]."""
    z = rng.standard_normal() if level.sigma > 0 else 0.0  # sigma 0 draws nothing: same stream as an exact learner
    return float(np.clip(0.5 + (1.0 - level.anchor) * (x - 0.5) + level.sigma * z, 0.0, 1.0))


def rank_positions(stat: np.ndarray, live: np.ndarray) -> np.ndarray:
    """Mid-quantile position in [0, 1] of every live entry of `stat` (equal values share one, nan elsewhere).
    Same rule as `abstraction.quantile_buckets`, so `int(pos * k)` is that bucket."""
    out = np.full(len(stat), np.nan)
    vals, inv = np.unique(stat[live], return_inverse=True)
    mass = np.bincount(inv, minlength=len(vals)) / live.sum()
    out[live] = (np.cumsum(mass) - mass / 2)[inv]
    return out


def step_of_value(x: float, sorted_live: np.ndarray, k: int) -> int:
    """The step a hand whose statistic is `x` would get among the live hands (`sorted_live`, ascending)."""
    n = len(sorted_live)
    lo = np.searchsorted(sorted_live, x, "left")
    hi = np.searchsorted(sorted_live, x, "right")
    return min(int((lo + (hi - lo) / 2) / n * k), k - 1)


def chip_equity_form(stat: np.ndarray, hole: int, k: int, level: Level, rng: np.random.Generator) -> int:
    """Form A: `stat` = every combo's equity against the opponent's range (nan on board collisions)."""
    live = ~np.isnan(stat)
    return step_of_value(perceive(float(stat[hole]), level, rng), np.sort(stat[live]), k)


def chip_pct_form(stat: np.ndarray, hole: int, k: int, level: Level, rng: np.random.Generator) -> int:
    """Form B: `stat` = every combo's strength statistic (hand rank among all hands; nan on collisions)."""
    pos = rank_positions(stat, ~np.isnan(stat))
    return min(int(perceive(float(pos[hole]), level, rng) * k), k - 1)
