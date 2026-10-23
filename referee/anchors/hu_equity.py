"""Heads-up preflop all-in equity between the 169 hand classes.

    python -m referee.anchors.hu_equity [--seed 20261024] [--nsim 20000] [--workers N]

`E[i, j]` is the equity (ties count half) of a random combo of class i against a random
non-conflicting combo of class j, run out to five board cards. `N[i, j]` is the number of
non-conflicting (combo of i, combo of j) pairs, which is how card removal enters callers'
ranges. Equity is Monte Carlo with a seed per class pair, so the table does not depend on
worker count; `N` is exact.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np

from stalker.core import evaluator as _ev
from stalker.core.cards import COMBO_CLASS, COMBOS, HAND_CLASSES

TABLE_PATH = Path(__file__).resolve().parent / "data" / "hu_class_equity.json"
DEFAULT_SEED = 20261024
DEFAULT_NSIM = 20000
N_CLASSES = len(HAND_CLASSES)

_SH = np.array(_ev._STRAIGHT_HIGH, dtype=np.int64)
_POP = np.array(_ev._POPCNT, dtype=np.int64)


def _top_table(k: int, shifts) -> np.ndarray:
    out = np.zeros(8192, dtype=np.int64)
    for m in range(8192):
        v = 0
        for r, sh in zip(_ev._TOP_RANKS[m][:k], shifts):
            v |= r << sh
        out[m] = v
    return out


_HI = np.array([t[0] if t else -1 for t in _ev._TOP_RANKS], dtype=np.int64)
_KICK5 = _top_table(5, (16, 12, 8, 4, 0))
_KICK3 = _top_table(3, (12, 8, 4))
_KICK2 = _top_table(2, (12, 8))
_BIT = np.int64(1) << np.arange(13, dtype=np.int64)


def _clear(mask: np.ndarray, r: np.ndarray) -> np.ndarray:
    return np.where(r >= 0, mask & ~(np.int64(1) << np.maximum(r, 0)), mask)


def evaluate_batch(hands: np.ndarray) -> np.ndarray:
    """Vectorised `stalker.core.evaluator.evaluate` for an (n, 7) card array; same scores."""
    hands = np.asarray(hands, dtype=np.int64)
    r = hands >> 2
    s = hands & 3
    cnt = (r[:, :, None] == np.arange(13)).sum(axis=1)
    bits = np.int64(1) << r
    smask = np.stack([np.where(s == k, bits, 0).sum(axis=1) for k in range(4)], axis=1)
    fl = smask[np.arange(len(hands)), _POP[smask].argmax(axis=1)]
    has_fl = _POP[fl] >= 5
    sf_hi = _SH[fl]

    def m(n):
        return ((cnt == n) * _BIT).sum(axis=1)

    m4, m3, m2, m1 = m(4), m(3), m(2), m(1)
    rank_mask = m4 | m3 | m2 | m1
    quads = _HI[m4]
    trips = _HI[m3]
    trips2 = _HI[_clear(m3, trips)]
    p0 = _HI[m2]
    m2b = _clear(m2, p0)
    p1 = _HI[m2b]
    p2 = _HI[_clear(m2b, p1)]
    st_hi = _SH[rank_mask]
    pair_r = np.maximum(trips2, p0)
    quad_kick = _HI[_clear(rank_mask, quads)]
    two_rest = m1 | np.where(p2 >= 0, np.int64(1) << np.maximum(p2, 0), 0)

    conds = [
        has_fl & (sf_hi >= 0),
        has_fl,
        quads >= 0,
        (trips >= 0) & (pair_r >= 0),
        st_hi >= 0,
        trips >= 0,
        p1 >= 0,
        p0 >= 0,
    ]
    vals = [
        (_ev.STRAIGHT_FLUSH << 20) | (sf_hi << 16),
        (_ev.FLUSH << 20) | _KICK5[fl],
        (_ev.QUADS << 20) | (quads << 16) | (quad_kick << 12),
        (_ev.FULL_HOUSE << 20) | (trips << 16) | (pair_r << 12),
        (_ev.STRAIGHT << 20) | (st_hi << 16),
        (_ev.TRIPS << 20) | (trips << 16) | _KICK2[m1],
        (_ev.TWO_PAIR << 20) | (p0 << 16) | (p1 << 12) | (_HI[two_rest] << 8),
        (_ev.PAIR << 20) | (p0 << 16) | _KICK3[m1],
    ]
    return np.select(conds, vals, default=(_ev.HIGH << 20) | _KICK5[m1])


@lru_cache(maxsize=1)
def class_combos() -> list[np.ndarray]:
    """For each class (HAND_CLASSES order), its combos as an (n, 2) card array."""
    idx = {c: i for i, c in enumerate(HAND_CLASSES)}
    groups: list[list[tuple[int, int]]] = [[] for _ in HAND_CLASSES]
    for combo, cls in zip(COMBOS, COMBO_CLASS):
        groups[idx[cls]].append(combo)
    return [np.array(g, dtype=np.int64) for g in groups]


def _pairs(i: int, j: int) -> np.ndarray:
    a, b = class_combos()[i], class_combos()[j]
    ok = ((a[:, None, :, None] != b[None, :, None, :]).all(axis=(2, 3)))
    ia, ib = np.nonzero(ok)
    return np.concatenate([a[ia], b[ib]], axis=1)


def pair_counts() -> np.ndarray:
    """Exact N[i, j]: non-conflicting combo pairs per class pair."""
    out = np.zeros((N_CLASSES, N_CLASSES), dtype=np.int64)
    for i in range(N_CLASSES):
        for j in range(i, N_CLASSES):
            out[i, j] = out[j, i] = len(_pairs(i, j))
    return out


def pair_equity(i: int, j: int, nsim: int, rng: np.random.Generator) -> float:
    pairs = _pairs(i, j)
    pick = pairs[rng.integers(len(pairs), size=nsim)]
    keys = rng.random((nsim, 52))
    np.put_along_axis(keys, pick, np.inf, axis=1)
    board = np.argpartition(keys, 5, axis=1)[:, :5]
    a = evaluate_batch(np.concatenate([pick[:, :2], board], axis=1))
    b = evaluate_batch(np.concatenate([pick[:, 2:], board], axis=1))
    return float(((a > b) + 0.5 * (a == b)).mean())


def _row(args) -> list[float]:
    i, seed, nsim = args
    return [pair_equity(i, j, nsim, np.random.default_rng([seed, i, j]))
            for j in range(i + 1, N_CLASSES)]


def build(seed: int = DEFAULT_SEED, nsim: int = DEFAULT_NSIM, workers: int = 1) -> dict:
    jobs = [(i, seed, nsim) for i in range(N_CLASSES)]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(_row, jobs, chunksize=1))
    else:
        rows = [_row(j) for j in jobs]
    eq = np.full((N_CLASSES, N_CLASSES), 0.5)
    for i, row in enumerate(rows):
        for k, v in enumerate(row):
            eq[i, i + 1 + k] = v
            eq[i + 1 + k, i] = 1.0 - v
    return {"classes": HAND_CLASSES, "seed": seed, "nsim": nsim,
            "equity": np.round(eq, 4).tolist(), "pairs": pair_counts().tolist()}


@lru_cache(maxsize=1)
def load() -> tuple[np.ndarray, np.ndarray]:
    """(E, N) as float arrays in HAND_CLASSES order."""
    if not TABLE_PATH.exists():
        raise FileNotFoundError(f"{TABLE_PATH} missing; run `python -m referee.anchors.hu_equity`")
    d = json.loads(TABLE_PATH.read_text())
    if d["classes"] != HAND_CLASSES:
        raise ValueError(f"{TABLE_PATH} class order differs from HAND_CLASSES; rebuild the table.")
    return np.array(d["equity"], dtype=float), np.array(d["pairs"], dtype=float)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m referee.anchors.hu_equity")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--nsim", type=int, default=DEFAULT_NSIM)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", type=Path, default=TABLE_PATH)
    a = ap.parse_args(argv)
    d = build(a.seed, a.nsim, a.workers)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    rows = ",\n".join("  " + json.dumps(k) + ": " + json.dumps(v) for k, v in d.items())
    a.out.write_text("{\n" + rows + "\n}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
