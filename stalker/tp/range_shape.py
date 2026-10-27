"""`opp.range` as shape + strength distribution (TP v1 candidate, #159, ADR 0011).

A single "tight–loose" or "top X%" answer can only describe a linear range. Strong players read
polar (nuts + bluffs, no middle), condensed (middle only) and capped (no nuts) ranges. Here a range
is summarised on the current board by five strength bins and a shape label computed from them:

- strength of an opponent combo = its showdown equity against MY range on this board
  (`stalker.tp.reference.equity`, exact; turn and river only — the flop needs a sampler).
- bins (weakest → strongest): [0,25) [25,50) [50,75) [75,90) [90,100] percent. Draft edges.
- shape, from the bin masses b1..b5 (draft thresholds, ADR 0011):
    polar      b1 + b5 >= 0.55 and b3 <= 0.20
    condensed  b2 + b3 + b4 >= 0.70 and b5 < 0.08
    linear     b4 + b5 >= b3 >= b1 + b2  (mass grows with strength) and b1 <= 0.20
    merged     anything else
  capped (a flag on top of the shape): the opponent's b5 < 0.5 x my b5.
- grading the 5-bin answer: earth mover's distance on the ordered bins, scaled to 0..1.
- beginner input is the width only ("top X% of hands"): `width_default` turns it into a linear
  5-bin distribution (tighter -> more mass in the strong bins), graded the same way.

Bins are equity bins against my range, not hand categories: a draw already sits in the bin of its
equity, so a separate "draw" bin would double-count and need a street-dependent outs definition
(#159 proposed one; dropped here, reason in the PR). "Narrow value" is not a separate shape: it is a
linear range with a small width (see `width_default`).

Inputs are public cards plus explicit ranges (TeacherContext stand-ins); no hidden cards.
"""
from __future__ import annotations

import numpy as np

from stalker.tp.reference import equity

EDGES = (0.25, 0.50, 0.75, 0.90)
BIN_NAMES = ("에어", "약함", "중간", "강함", "넛급")
SHAPES = ("polar", "condensed", "linear", "merged")


def _bin(e: float) -> int:
    return int(np.searchsorted(EDGES, e, side="right"))


def strength_bins(opp_range, my_range, board) -> np.ndarray:
    """Mass of the opponent range in each strength bin (sums to 1)."""
    board = tuple(board)
    if len(board) not in (4, 5):
        raise ValueError("strength bins are exact on the turn and river only; the flop needs a sampler")
    mass = np.zeros(5)
    for combo, w in opp_range:
        if w <= 0 or set(combo) & set(board):
            continue
        mine = [(h, wh) for h, wh in my_range if not set(h) & set(combo)]
        if not mine:
            continue
        mass[_bin(equity(combo, board, [mine])["equity"])] += w
    if mass.sum() == 0:
        raise ValueError("no opponent combo is compatible with the board and my range")
    return mass / mass.sum()


def shape_of(b) -> str:
    b1, b2, b3, b4, b5 = (float(x) for x in b)
    if b1 + b5 >= 0.55 and b3 <= 0.20:
        return "polar"
    if b2 + b3 + b4 >= 0.70 and b5 < 0.08:
        return "condensed"
    if b4 + b5 >= b3 >= b1 + b2 and b1 <= 0.20:
        return "linear"
    return "merged"


def capped(opp_bins, my_bins) -> bool:
    return float(opp_bins[4]) < 0.5 * float(my_bins[4])


# Quick-entry templates: choosing a shape pre-fills the five bars, the user then nudges them.
TEMPLATES = {
    "polar": (0.40, 0.05, 0.05, 0.10, 0.40),
    "condensed": (0.05, 0.30, 0.40, 0.25, 0.00),
    "linear": (0.05, 0.10, 0.20, 0.30, 0.35),
    "merged": (0.20, 0.20, 0.20, 0.20, 0.20),
}


def emd(user, truth) -> float:
    """Earth mover's distance between two 5-bin distributions, 0 (same) .. 1 (all mass at opposite ends)."""
    u, t = np.asarray(user, float), np.asarray(truth, float)
    if u.shape != (5,) or t.shape != (5,) or abs(u.sum() - 1) > 1e-6 or abs(t.sum() - 1) > 1e-6:
        raise ValueError("emd needs two 5-bin distributions that each sum to 1")
    return float(np.abs(np.cumsum(u - t))[:-1].sum() / 4)


def score(user, truth) -> int:
    """0–100 grade of a 5-bin answer."""
    return int(round(100 * (1 - emd(user, truth))))


TIGHT = (0.00, 0.05, 0.15, 0.30, 0.50)   # top ~5% of hands
LOOSE = (0.25, 0.25, 0.25, 0.15, 0.10)   # top ~80%


def width_default(width: float) -> tuple[float, ...]:
    """Beginner answer "top X%" (0.05..0.80) as a linear 5-bin distribution, interpolated tight -> loose."""
    if not 0 < width <= 1:
        raise ValueError("width is the share of starting hands, 0 < width <= 1")
    a = min(max((width - 0.05) / 0.75, 0.0), 1.0)
    return tuple((1 - a) * t + a * l for t, l in zip(TIGHT, LOOSE))
