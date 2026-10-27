"""Card abstraction for the unconstrained E2 baseline: hand-strength buckets per board.

Preflop: the 169 hand classes. Postflop: expected hand strength against a uniformly random hand,
estimated by dealing `RUNOUTS` random completions of the board and ranking all 1326 combos at once
with the vectorised evaluator; bucket = floor(EHS x N_BUCKETS). One call buckets every combo on a
board, so the opponent-range computations in LBR reuse the same table. Seeded and cached by board.

TP tiers (#187) see only hand.pct — the hand's percentile against a random hand — on a k-step
quantile scale (each step holds about 1/k of the live combos, as in E1). `Abstraction` names either
the baseline above or such a tier; MCCFR keys infosets with it and LBR buckets the opponent with it.
"""
from __future__ import annotations

from dataclasses import dataclass
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
    rng = np.random.default_rng(abs(hash(board)) % (2 ** 32))
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
        ranks = np.empty(len(idx))
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


def quantile_buckets(x: np.ndarray, w: np.ndarray, k: int) -> np.ndarray:
    """k-step quantile scale of x under weights w; equal values share a step (-1 where w == 0)."""
    out = np.full(len(x), -1)
    live = w > 0
    vals, inv = np.unique(x[live], return_inverse=True)
    mass = np.bincount(inv, w[live], len(vals)) / w[live].sum()
    mid = np.cumsum(mass) - mass / 2
    out[live] = np.minimum((mid * k).astype(int), k - 1)[inv]
    return out


@lru_cache(maxsize=1)
def _class_weights() -> np.ndarray:
    w = np.zeros(len(HAND_CLASSES))
    for a, b in COMBOS:
        w[preflop_bucket(a, b)] += 1
    return w


@lru_cache(maxsize=None)
def _preflop_pct_buckets(k: int) -> np.ndarray:
    from referee.anchors.hu_equity import load

    E, N = load()
    vs_random = (N * E).sum(axis=1) / N.sum(axis=1)
    return quantile_buckets(vs_random, _class_weights(), k)


@lru_cache(maxsize=200_000)
def _postflop_pct_buckets(board: tuple[int, ...], k: int) -> np.ndarray:
    e = ehs_table(board)
    ok = ~np.isnan(e)
    return quantile_buckets(np.nan_to_num(e), ok.astype(float), k)


@dataclass(frozen=True)
class Abstraction:
    """Card abstraction: `pre_k`/`post_k` = None is the baseline (169 classes / EHS x N_BUCKETS)."""
    pre_k: int | None = None
    post_k: int | None = None

    @property
    def name(self) -> str:
        return "baseline" if self == BASELINE else f"pct{self.pre_k or 169}x{self.post_k or N_BUCKETS}"

    def bucket(self, hole: tuple[int, int], board: tuple[int, ...]) -> int:
        if not board:
            c = preflop_bucket(*hole)
            return c if self.pre_k is None else int(_preflop_pct_buckets(self.pre_k)[c])
        if self.post_k is None:
            return postflop_bucket(hole[0], hole[1], board)
        a, b = hole
        return int(_postflop_pct_buckets(tuple(board), self.post_k)[COMBO_INDEX[(a, b) if a > b else (b, a)]])

    def combo_buckets(self, board: tuple[int, ...]) -> np.ndarray:
        """Bucket of every one of the 1326 combos (-1 where a combo collides with the board)."""
        if not board:
            cls = _combo_classes()
            return cls if self.pre_k is None else _preflop_pct_buckets(self.pre_k)[cls]
        if self.post_k is None:
            e = ehs_table(tuple(board))
            return np.where(np.isnan(e), -1, np.minimum((np.nan_to_num(e) * N_BUCKETS).astype(int), N_BUCKETS - 1))
        return _postflop_pct_buckets(tuple(board), self.post_k)

    def to_json(self) -> dict:
        return {"pre_k": self.pre_k, "post_k": self.post_k}

    @classmethod
    def from_json(cls, d: dict | None) -> "Abstraction":
        return cls(**d) if d else BASELINE


@lru_cache(maxsize=1)
def _combo_classes() -> np.ndarray:
    return np.array([preflop_bucket(a, b) for a, b in COMBOS])


BASELINE = Abstraction()
# TP resolutions (docs/TP.md tiers, as in E1): beginner 5 steps, mid 11. The baseline stands in for
# the finest tier until a finer postflop table is affordable.
TIERS = {"beginner": Abstraction(5, 5), "mid": Abstraction(11, 11), "baseline": BASELINE}
