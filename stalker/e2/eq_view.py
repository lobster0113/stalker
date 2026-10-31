"""E2-4: the TP view `hand.equity` — equity against the opponent's range, on a k-step quantile scale (#188).

Each seat's range is the reach probability of all 1326 combos, Bayes-updated from that seat's own
strategy at every public action (no hidden cards: the info contract). At a decision, every combo of
the acting seat gets its equity against the opponent's range, and the TP value is that equity's
quantile step (beginner 5, mid 11), as in E1/E1m. Training is external-sampling MCCFR that carries
both ranges down the walk, so ranges, bluffs and counters co-evolve with the strategy.

Equity: preflop from the 169-class table (`referee.anchors.hu_equity`); postflop from cached runout
scores per board, so equity against any range is a weighted cumulative sum. Approximation: a range
combo that shares a card with mine is not removed (board collisions are).

    python -m stalker.e2.eq_view --tier beginner --iters 2000 --hands 400
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from functools import lru_cache

import numpy as np

from stalker.core import fast_eval
from stalker.core.fast_eval import evaluate_batch  # compiled when numba is installed (#201), same scores
from stalker.core.cards import COMBO_INDEX, COMBOS
from stalker.e2 import game as G
from stalker.e2.abstraction import _class_weights, _combo_classes, quantile_buckets
from stalker.e2.mccfr import MCCFR

N = len(COMBOS)
COMBO_ARR = np.array(COMBOS, dtype=np.int64)
EQ_TIERS = {"beginner": 5, "mid": 11}
EQ_RUNOUTS = 12  # sampled turn/river completions per board; equity granularity ~1/12


def combo_index(hole: tuple[int, int]) -> int:
    a, b = hole
    return COMBO_INDEX[(a, b) if a > b else (b, a)]


@lru_cache(maxsize=1)
def _class_table() -> tuple[np.ndarray, np.ndarray]:
    from referee.anchors.hu_equity import load

    E, Np = load()
    return Np * E, Np


@lru_cache(maxsize=256)  # boards rarely repeat across deals; ~0.4 MB each (4096 reached GBs per process)
def _runouts(board: tuple[int, ...]) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Per sampled runout: usable combo indices, their order by score, and tie-group bounds."""
    # Seed from the cards themselves: hash() of a tuple holding a str changes per process.
    rng = np.random.default_rng([20261028, *board])
    live = np.array([c for c in range(52) if c not in board])
    ok = ~_board_dead(board)
    need = 5 - len(board)
    out = []
    for _ in range(EQ_RUNOUTS if need else 1):
        extra = rng.choice(live, size=need, replace=False) if need else np.array([], dtype=np.int64)
        full = np.concatenate([np.array(board, dtype=np.int64), extra])
        gone = np.zeros(52, dtype=bool)   # mask lookup instead of np.isin: same set, ~10x cheaper (#454)
        gone[extra] = True
        idx = np.flatnonzero(ok & ~(gone[COMBO_ARR[:, 0]] | gone[COMBO_ARR[:, 1]]))
        score = evaluate_batch(np.concatenate([COMBO_ARR[idx], np.broadcast_to(full, (len(idx), 5))], axis=1))
        order = np.argsort(score, kind="stable")
        s_sorted = score[order]
        out.append((idx, order, np.searchsorted(s_sorted, score, "left"), np.searchsorted(s_sorted, score, "right")))
    return out


def _runout_fulls(board: tuple[int, ...]) -> np.ndarray:
    """The sampled runouts as rows of 5 cards (board + drawn cards); the rng draws are the contract for the keys."""
    rng = np.random.default_rng([20261028, *board])
    live = np.array([c for c in range(52) if c not in board])
    need = 5 - len(board)
    b = np.array(board, dtype=np.int64)
    rows = [np.concatenate([b, rng.choice(live, size=need, replace=False) if need else np.array([], dtype=np.int64)])
            for _ in range(EQ_RUNOUTS if need else 1)]
    return np.stack(rows)


@lru_cache(maxsize=256)
def _flat_runouts(board: tuple[int, ...]):
    """`_runouts` concatenated for the compiled kernel: idx, order, lo, hi, segment offsets."""
    if fast_eval.HAVE_NUMBA:
        return fast_eval.runout_tables(COMBO_ARR, ~_board_dead(board), _runout_fulls(board), len(board))
    rs = _runouts(board)
    off = np.cumsum([0] + [len(r[0]) for r in rs])
    return (np.concatenate([r[0] for r in rs]), np.concatenate([r[1] for r in rs]),
            np.concatenate([r[2] for r in rs]), np.concatenate([r[3] for r in rs]), off.astype(np.int64))


def equity_vs(board: tuple[int, ...], w: np.ndarray) -> np.ndarray:
    """Equity of every combo against range weights `w` (nan where the combo collides with the board)."""
    if not board:
        num, den = _class_table()
        cls = _combo_classes()
        wc = np.bincount(cls, w, num.shape[0]) / _class_weights()
        # Not `den @ wc`: BLAS picks its kernel per CPU and each sums in its own order, so the last bits
        # differed between CI runners and flipped E3 equity steps (#447). numpy's row reduction is the
        # same pairwise order on every CPU.
        d = (den * wc).sum(axis=1)
        eq = np.divide((num * wc).sum(axis=1), d, out=np.full(len(d), 0.5), where=d > 0)
        return eq[cls]
    acc, cnt = np.zeros(N), np.zeros(N)
    if fast_eval.HAVE_NUMBA:
        fast_eval.equity_segments(np.ascontiguousarray(w, dtype=np.float64), *_flat_runouts(tuple(board)), acc, cnt)
        out = np.divide(acc, cnt, out=np.full(N, 0.5), where=cnt > 0)
        out[_board_dead(tuple(board))] = np.nan
        return out
    for idx, order, lo, hi in _runouts(tuple(board)):
        ww = w[idx]
        cw = np.concatenate([[0.0], np.cumsum(ww[order])])
        below, upto = cw[lo], cw[hi]
        tot = cw[-1] - ww
        tie = upto - below - ww  # equal scores, excluding the combo itself
        good = tot > 0
        acc[idx[good]] += (below[good] + 0.5 * tie[good]) / tot[good]
        cnt[idx[good]] += 1
    out = np.divide(acc, cnt, out=np.full(N, 0.5), where=cnt > 0)
    out[_board_dead(tuple(board))] = np.nan
    return out


@lru_cache(maxsize=256)
def _board_dead(board: tuple[int, ...]) -> np.ndarray:
    return np.isin(COMBO_ARR, list(board)).any(axis=1)


def equity_vs_many(board: tuple[int, ...], W: np.ndarray) -> np.ndarray:
    """Row r: equity of every combo against range W[r] (several opponents, E3). Row by row: a 2-D
    gather was slower than the 1-D path for these sizes (measured)."""
    return np.stack([equity_vs(board, w) for w in W])


def eq_buckets(board: tuple[int, ...], opp_range: np.ndarray, k: int) -> np.ndarray:
    """k-step quantile of equity vs the opponent's range, for every combo (-1 on board collisions)."""
    eq = equity_vs(tuple(board), opp_range)
    live = ~np.isnan(eq)
    return quantile_buckets(np.nan_to_num(eq), live.astype(float), k)


def _hist(s: G.State) -> str:
    return "".join(h if len(h) == 1 else h[1:] for h in s.history)


class EqView:
    """Bucket map of a seat at a public state, given both public ranges (shared by MCCFR and LBR)."""
    dynamic = True

    def __init__(self, k: int):
        self.k = k

    def buckets(self, s: G.State, seat: int, ranges: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
        return eq_buckets(s.board, ranges[1 - seat], self.k)

    def to_json(self) -> dict:
        return {"view": "equity", "k": self.k}


def seat_probs(get, s: G.State, seat: int, b: np.ndarray, n_acts: int) -> np.ndarray:
    """(1326, n_acts): the seat's action probabilities per combo; uniform where the policy is silent."""
    out = np.full((N, n_acts), 1.0 / n_acts)
    hist = _hist(s)
    for v in np.unique(b):
        if v < 0:
            continue
        p = get(f"{seat}|{s.street}|{v}|{hist}")
        if p is not None and len(p) == n_acts:
            out[b == v] = p
    out[b < 0] = 0.0
    return out


class EqMCCFR(MCCFR):
    """External-sampling MCCFR whose infosets are (seat, street, equity-vs-range step, public history)."""

    def __init__(self, seed: int = 0, k: int = 5):
        super().__init__(seed)
        self.view = EqView(k)

    def iterate(self, n: int = 1) -> None:
        for _ in range(n):
            self.iterations += 1
            s = G.deal(self.rng)
            for trav in (0, 1):
                self._walk_r(s, (np.ones(N), np.ones(N)), trav)

    def _walk_r(self, s: G.State, ranges, trav: int) -> float:
        if s.done:
            v = G.payoff(s) / G.BB
            return v if trav == 0 else -v
        acts = G.legal(s)
        p = s.to_act
        b = self.view.buckets(s, p, ranges)
        mine = int(b[combo_index(s.hole[p])])
        key = f"{p}|{s.street}|{mine}|{_hist(s)}"
        sigma = self._sigma(key, len(acts))
        probs = seat_probs(lambda k_: self._sigma(k_, len(acts)), s, p, b, len(acts))

        def child(i):
            r = list(ranges)
            r[p] = ranges[p] * probs[:, i]
            return G.apply(s, acts[i]), (r[0], r[1])

        if p == trav:
            vals = np.array([self._walk_r(*child(i), trav=trav) for i in range(len(acts))])
            v = float(sigma @ vals)
            r = self.regret.setdefault(key, np.zeros(len(acts)))
            np.maximum(r + (vals - v), 0, out=r)
            return v
        i = self.rng.choice(len(acts), p=sigma)
        avg = self.avg[key]
        self.avg[key] = (avg if avg is not None else 0) + self.iterations * sigma
        return self._walk_r(*child(i), trav=trav)


def main(argv=None) -> int:
    from referee.e2.lbr import exploitability_lb

    ap = argparse.ArgumentParser(description="E2-4 equity-vs-range TP view: train and LBR (local reference)")
    ap.add_argument("--tier", choices=sorted(EQ_TIERS), default="beginner")
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    m = EqMCCFR(a.seed, EQ_TIERS[a.tier])
    t0 = time.monotonic()
    m.iterate(a.iters)
    dt = time.monotonic() - t0
    lb = exploitability_lb(m.policy(), a.hands, seed=a.seed * 1000 + 7, view=m.view)
    print(json.dumps({"tier": a.tier, "view": "equity", "iters": a.iters, "iters_per_s": round(a.iters / dt, 2),
                      "infosets": len(m.regret), **lb}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
