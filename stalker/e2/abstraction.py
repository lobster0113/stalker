"""Card abstraction for the unconstrained E2 baseline: hand-strength buckets per board.

Preflop: the 169 hand classes. Postflop: expected hand strength against a uniformly random hand,
estimated by dealing `RUNOUTS` random completions of the board and ranking all 1326 combos at once
with the vectorised evaluator; bucket = floor(EHS x N_BUCKETS). One call buckets every combo on a
board, so the opponent-range computations in LBR reuse the same table. Seeded and cached by board.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from referee.anchors.hu_equity import evaluate_batch
from stalker.core.cards import COMBO_INDEX, COMBOS, hand_class, HAND_CLASSES

N_BUCKETS = 10
RUNOUTS = 6
COMBO_ARR = np.array(COMBOS, dtype=np.int64)
CLASS_INDEX = {c: i for i, c in enumerate(HAND_CLASSES)}


def preflop_bucket(a: int, b: int) -> int:
    return CLASS_INDEX[hand_class(a, b)]


@lru_cache(maxsize=200_000)
def ehs_table(board: tuple[int, ...]) -> np.ndarray:
    """EHS of every combo on `board` (nan for combos that collide with the board)."""
    rng = np.random.default_rng([20261027, *board])  # seeded by the cards themselves, process-independent
    live = np.array([c for c in range(52) if c not in board])
    ok = ~np.isin(COMBO_ARR, list(board)).any(axis=1)
    acc = np.zeros(len(COMBOS))
    for _ in range(RUNOUTS):
        need = 5 - len(board)
        extra = rng.choice(live, size=need, replace=False) if need else np.array([], dtype=np.int64)
        full = np.concatenate([np.array(board, dtype=np.int64), extra])
        usable = ok & ~np.isin(COMBO_ARR, extra).any(axis=1)
        idx = np.flatnonzero(usable)
        hands = np.concatenate([COMBO_ARR[idx], np.broadcast_to(full, (len(idx), 5))], axis=1)
        score = evaluate_batch(hands)
        order = np.argsort(score, kind="stable")
        # Share of other usable combos this combo beats (ties count half).
        s_sorted = score[order]
        lo = np.searchsorted(s_sorted, score, side="left")
        hi = np.searchsorted(s_sorted, score, side="right")
        ranks = (lo + (hi - lo - 1) / 2) / max(len(idx) - 1, 1)
        acc[idx] += ranks
        acc[~usable & ok] += 0.5  # a combo blocked only by this runout: neutral contribution
    out = acc / RUNOUTS
    out[~ok] = np.nan
    return out


def postflop_bucket(a: int, b: int, board: tuple[int, ...]) -> int:
    e = ehs_table(tuple(board))[COMBO_INDEX[(a, b) if a > b else (b, a)]]
    return min(int(e * N_BUCKETS), N_BUCKETS - 1)


def bucket(hole: tuple[int, int], board: tuple[int, ...]) -> int:
    return preflop_bucket(*hole) if not board else postflop_bucket(hole[0], hole[1], board)
