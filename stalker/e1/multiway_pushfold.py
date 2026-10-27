"""E1m: 3-handed short-stack push/fold with ICM — the first multiway check of the TP bottleneck (#181).

Game and exact evaluation come from `referee.anchors.icm_reference` (seats in preflop order, the
last two are SB and BB; first all-in, then callers in order, the first caller ends the action).
The TP bottleneck policy sees only quantised TP values plus position (DecisionContext):

- pusher (first in): one of three multiway summaries of "how strong am I", on a rank scale —
    "rank"       hand.pct: quantile of the hand against a random hand (no opponent model)
    "strongest"  equity against the calling range of the opponent most likely to call
    "per_opp"    a pair of quantised equities, one per opponent behind (2-D bucket)
    "composite"  equity against the call-probability-weighted mix of the callers' ranges
- caller: equity against the pusher's shoving range (the only all-in opponent).

Training is fictitious play between the bottleneck policies (each seat best-responds in bucket
space to the others' average), so ranges, bluffs and counters co-evolve. The result is judged by
the reference's exact per-seat best-response gains.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from referee.anchors import icm_reference as R

TIER_LEVELS = {"beginner": 5, "mid": 11, "pro": 101}
VIEWS = ("rank", "strongest", "per_opp", "composite")


def _quantile(x: np.ndarray, w: np.ndarray, k: int) -> np.ndarray:
    order = np.argsort(x, kind="stable")
    cum = np.cumsum(w[order]) / w.sum()
    out = np.empty(len(x), dtype=int)
    out[order] = np.minimum(((cum - w[order] / w.sum() / 2) * k).astype(int), k - 1)
    return out


def _eq_vs(tree, rng_w: np.ndarray) -> np.ndarray:
    """Equity of each class against a range (class weights), with exact pair-count card removal."""
    W = tree.N * rng_w[None, :]
    den = W.sum(axis=1)
    return np.divide((W * tree.E).sum(axis=1), den, out=np.full(R.N_CLASSES, 0.5), where=den > 0)


@dataclass
class Result:
    view: str
    tier: str
    value_model: str
    gains: np.ndarray          # per-seat exact best-response gain (share of prize pool / chips)
    exploitability: float      # sum of gains, as a share of the scale
    nash_gains: np.ndarray
    strategy: R.Strategy | None = None   # the delivered bottleneck policy (strategy browser, #189)


def _buckets(tree, st: R.Strategy, n: int, view: str, k: int):
    """Bucket maps: push[p] -> (classes,) ints; call[(q, p)] -> (classes,) ints."""
    rank = _quantile(_eq_vs(tree, np.ones(R.N_CLASSES)), R.CLASS_COMBOS, k)
    push, call = {}, {}
    for p in range(n - 1):
        behind = list(range(p + 1, n))
        if view == "rank":
            push[p] = rank
        else:
            eqs = [_eq_vs(tree, st.call[q, p]) for q in behind]
            freq = np.array([R.PRIOR @ st.call[q, p] for q in behind])
            if view == "strongest":
                push[p] = _quantile(eqs[int(freq.argmax())], R.CLASS_COMBOS, k)
            elif view == "composite":
                mix = sum(f * st.call[q, p] for f, q in zip(freq, behind))
                push[p] = _quantile(_eq_vs(tree, mix), R.CLASS_COMBOS, k)
            else:  # per_opp: a combined code of one quantile per opponent behind
                code = np.zeros(R.N_CLASSES, dtype=int)
                for e in eqs:
                    code = code * k + _quantile(e, R.CLASS_COMBOS, k)
                push[p] = code
        for q in behind:
            call[q, p] = _quantile(_eq_vs(tree, st.push[p]), R.CLASS_COMBOS, k)
    return push, call


def _bucket_br(ev: R.Evaluation, st: R.Strategy, push_b, call_b) -> R.Strategy:
    br = st.copy()
    for p, (e, fold) in ev.push_ev.items():
        b = push_b[p]
        gain = np.bincount(b, R.PRIOR * (e - fold), b.max() + 1)
        br.push[p] = (gain > 0).astype(float)[b]
    for (q, p), (e, fold, mass) in ev.call_ev.items():
        b = call_b[q, p]
        gain = np.bincount(b, mass * (e - fold), b.max() + 1)
        br.call[q, p] = (gain > 0).astype(float)[b]
    return br


def _project(st: R.Strategy, push_b, call_b) -> R.Strategy:
    out = st.copy()
    for p, b in push_b.items():
        num, den = np.bincount(b, R.PRIOR * st.push[p]), np.bincount(b, R.PRIOR)
        out.push[p] = (num / np.where(den > 0, den, 1))[b]
    for (q, p), b in call_b.items():
        num, den = np.bincount(b, R.PRIOR * st.call[q, p]), np.bincount(b, R.PRIOR)
        out.call[q, p] = (num / np.where(den > 0, den, 1))[b]
    return out


def train(spot: R.Spot, view: str = "rank", tier: str = "pro", value_model: str = "icm",
          iters: int = 2000) -> Result:
    if view not in VIEWS:
        raise ValueError(f"view {view!r}; use one of {VIEWS}")
    tree = R._Tree(spot, R._value_fn(spot, value_model, 0, R.BASELINE_TOL, iters))
    n, k = spot.n, TIER_LEVELS[tier]
    st = R.Strategy.uniform(n)
    for it in range(1, iters + 1):
        ev = tree.evaluate(st)
        push_b, call_b = _buckets(tree, st, n, view, k)
        br = _bucket_br(ev, st, push_b, call_b)
        a = 1.0 / (it + 1)
        st = R.Strategy(st.push + a * (br.push - st.push), st.call + a * (br.call - st.call))
    # Deliver a policy that is a function of its own TP values (bucketed against the final ranges).
    for _ in range(5):
        push_b, call_b = _buckets(tree, st, n, view, k)
        st = _project(st, push_b, call_b)
    scale = R._scale(spot, value_model)
    gains = tree.evaluate(st).gains(st, n) / scale
    nash = R._solve_tree(tree, scale, R.BASELINE_TOL, iters)
    return Result(view, tier, value_model, gains, float(gains.sum()), nash.gains / scale, st)


def table(stacks_bb=(8, 10, 15), payouts=(0.5, 0.3, 0.2), iters: int = 1500) -> list[dict]:
    rows = []
    for s in stacks_bb:
        spot = R.Spot((s * 100, s * 100, s * 100), 50, 100, payouts)
        for vm in ("icm", "chipev"):
            for view in VIEWS:
                for tier in ("beginner", "mid", "pro"):
                    if view == "per_opp" and tier == "pro":
                        continue  # 101 x 101 codes: effectively no bottleneck
                    r = train(spot, view, tier, vm, iters)
                    rows.append({"stack_bb": s, "value_model": vm, "view": view, "tier": tier,
                                 "exploitability": round(r.exploitability, 6),
                                 "nash_exploitability": round(float(r.nash_gains.sum()), 6),
                                 "gains": [round(float(g), 6) for g in r.gains]})
    return rows


if __name__ == "__main__":
    import json
    import sys

    for row in table(iters=int(sys.argv[1]) if len(sys.argv) > 1 else 1500):
        print(json.dumps(row), flush=True)
