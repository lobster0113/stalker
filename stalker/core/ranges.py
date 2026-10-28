"""Preflop hand strength ordering and range construction over the 1326 combos."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .cards import COMBO_CLASS, COMBOS, HAND_CLASSES, hand_class

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PREFLOP_TABLE = DATA_DIR / "preflop_equity.json"


@lru_cache(maxsize=1)
def preflop_equity() -> dict[str, list[float]]:
    """class -> [equity vs 1 random hand, vs 2, ... vs 5]. Built by `python -m stalker.tools.build_tables`."""
    if not PREFLOP_TABLE.exists():
        raise FileNotFoundError(f"{PREFLOP_TABLE} missing; run `python -m stalker.tools.build_tables`")
    return json.loads(PREFLOP_TABLE.read_text(encoding="utf-8"))


def class_equity(cls: str, n_opp: int = 1) -> float:
    eq = preflop_equity()[cls]
    return eq[min(max(n_opp, 1), len(eq)) - 1]


@lru_cache(maxsize=1)
def class_top_pct() -> dict[str, float]:
    """class -> midpoint 'top fraction' of all combos (0 = best hand, 1 = worst), ordered by HU equity."""
    eq = preflop_equity()
    order = sorted(HAND_CLASSES, key=lambda c: -eq[c][0])
    out = {}
    cum = 0
    for c in order:
        n = 6 if len(c) == 2 else (4 if c[2] == "s" else 12)
        out[c] = (cum + n / 2) / 1326
        cum += n
    return out


@lru_cache(maxsize=1)
def combo_top_pct() -> np.ndarray:
    t = class_top_pct()
    return np.array([t[c] for c in COMBO_CLASS])


def hand_top_pct(c1: int, c2: int) -> float:
    return class_top_pct()[hand_class(c1, c2)]


def top_range(p: float, lo: float = 0.0, softness: float = 0.02) -> np.ndarray:
    """Weights ~1 for combos whose top-pct lies in [lo, p], soft-edged."""
    pct = combo_top_pct()
    p = float(np.clip(p, 0.005, 1.0))
    w = 1.0 / (1.0 + np.exp((pct - p) / softness))
    if lo > 0:
        w *= 1.0 / (1.0 + np.exp((lo - pct) / softness))
    return w


def uniform_range() -> np.ndarray:
    return np.ones(len(COMBOS))
