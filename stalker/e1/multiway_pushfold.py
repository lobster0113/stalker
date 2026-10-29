"""E1m: 3-handed short-stack push/fold with ICM — the first multiway check of the TP bottleneck (#181).

Game and exact evaluation come from `referee.anchors.icm_reference` (seats in preflop order, the
last two are SB and BB; first all-in, then callers in order, the first caller ends the action).
The TP bottleneck policy sees only quantised TP values plus position (DecisionContext):

- pusher (first in): one of four multiway summaries of "how strong am I", on a rank scale —
    "rank"       hand.pct: quantile of the hand against a random hand (no opponent model)
    "strongest"  equity against the calling range of the opponent most likely to call
    "per_opp"    a pair of quantised equities, one per opponent behind (2-D bucket)
    "composite"  equity against the call-probability-weighted mix of the callers' ranges
- caller: equity against the pusher's shoving range (the only all-in opponent).

Training is fictitious play between the bottleneck policies (each seat best-responds in bucket
space to the others' average), so ranges, bluffs and counters co-evolve. The result is judged by
the reference's exact per-seat best-response gains, next to unconstrained fictitious play run for
the same number of iterations (no early stop), so the gap is the cost of the bottleneck alone.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from referee.anchors import icm_reference as R

TIER_LEVELS = {"beginner": 5, "mid": 11, "pro": 101}
TP_STEP = {"beginner": 25, "mid": 10, "pro": 1}   # points per scale step, as stalker.e1.tp_pushfold.TIER_STEP
VIEWS = ("rank", "strongest", "per_opp", "composite")


def _qpos(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Mid-rank position in [0, 1] of each class under weights w (the continuous TP value)."""
    order = np.argsort(x, kind="stable")
    cum = np.cumsum(w[order]) / w.sum()
    out = np.empty(len(x))
    out[order] = cum - w[order] / w.sum() / 2
    return out


def _quantile(x: np.ndarray, w: np.ndarray, k: int) -> np.ndarray:
    return np.minimum((_qpos(x, w) * k).astype(int), k - 1)


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
    nash_gains: np.ndarray     # unconstrained fictitious play, same iteration count
    strategy: R.Strategy | None = None   # the delivered policy

    @property
    def loss(self) -> float:
        """Exploitability above the unconstrained baseline (negative: the bottleneck converged faster)."""
        return self.exploitability - float(self.nash_gains.sum())


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


def baseline(spot: R.Spot, value_model: str, iters: int) -> np.ndarray:
    """Per-seat gains of unconstrained fictitious play after exactly `iters` iterations (tol=0)."""
    tree = R._Tree(spot, R._value_fn(spot, value_model, 0, R.BASELINE_TOL, iters))
    return R._solve_tree(tree, R._scale(spot, value_model), 0.0, iters).gains / R._scale(spot, value_model)


def train(spot: R.Spot, view: str = "rank", tier: str = "pro", value_model: str = "icm",
          iters: int = 2000, nash_gains: np.ndarray | None = None) -> Result:
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
    if nash_gains is None:
        nash_gains = baseline(spot, value_model, iters)
    return Result(view, tier, value_model, gains, float(gains.sum()), nash_gains, st)


def tp_values(tree, st: R.Strategy, n: int, view: str) -> dict[tuple, np.ndarray]:
    """TP value 0-100 per class at each decision: the mid-rank percentile behind `_buckets`, so
    bucket = min(int(value * k / 100), k - 1) and the bin edges are 100 j / k. per_opp has no scalar value."""
    if view == "per_opp":
        raise ValueError("per_opp reads a 2-D code, not one TP value; Gate S/F take rank, strongest or composite")
    rank = _qpos(_eq_vs(tree, np.ones(R.N_CLASSES)), R.CLASS_COMBOS)
    out = {}
    for p in range(n - 1):
        behind = list(range(p + 1, n))
        if view == "rank":
            out["push", p] = rank
        else:
            freq = np.array([R.PRIOR @ st.call[q, p] for q in behind])
            if view == "strongest":
                rng_w = st.call[behind[int(freq.argmax())], p]
            else:
                rng_w = sum(f * st.call[q, p] for f, q in zip(freq, behind))
            out["push", p] = _qpos(_eq_vs(tree, rng_w), R.CLASS_COMBOS)
        for q in behind:
            out["call", q, p] = _qpos(_eq_vs(tree, st.push[p]), R.CLASS_COMBOS)
    return {d: 100.0 * v for d, v in out.items()}


def decision_policy(spot: R.Spot, view: str = "composite", tier: str = "beginner", value_model: str = "icm",
                    iters: int = 1500) -> dict[tuple, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """The trained bottleneck policy as a map per decision: (TP value per class, bin edges, action
    probability per bin). Bins no hand reads take the nearest occupied bin's action (the lower one
    on a tie), as in the E1 Gate F policy, so a follower that misreads into them gets no artefact."""
    r = train(spot, view, tier, value_model, iters, nash_gains=np.zeros(spot.n))
    tree = R._Tree(spot, R._value_fn(spot, value_model, 0, R.BASELINE_TOL, iters))
    k = TIER_LEVELS[tier]
    edges = 100.0 * np.arange(1, k) / k
    out = {}
    for d, v in tp_values(tree, r.strategy, spot.n, view).items():
        probs = r.strategy.push[d[1]] if d[0] == "push" else r.strategy.call[d[1], d[2]]
        b = np.searchsorted(edges, v, side="right")
        den = np.bincount(b, R.PRIOR, k)
        occupied = np.flatnonzero(den > 0)
        bin_probs = np.bincount(b, R.PRIOR * probs, k) / np.where(den > 0, den, 1)
        nearest = occupied[np.abs(np.arange(k)[:, None] - occupied[None, :]).argmin(axis=1)]
        out[d] = (v, edges, bin_probs[nearest])
    return out


def gate_s_policy(view: str = "composite", tier: str = "beginner", iters: int = 1500):
    """E1m Gate S policy (#313): Spot -> {decision: (169 probs, TP bins)}; one ICM training per spot."""
    cache: dict[R.Spot, dict] = {}

    def policy(spot: R.Spot):
        if spot not in cache:
            cache[spot] = decision_policy(spot, view, tier, "icm", iters)
        return {d: (bp[np.searchsorted(e, v, side="right")], np.searchsorted(e, v, side="right"))
                for d, (v, e, bp) in cache[spot].items()}
    policy.tp_step_points = TP_STEP[tier]
    return policy


def gate_f_policy(view: str = "composite", tier: str = "beginner", iters: int = 1500):
    """E1m Gate F policy (#313): Spot -> {decision: FollowSpec}; one ICM training per spot."""
    from referee.gate_f import FollowSpec
    cache: dict[R.Spot, dict] = {}

    def policy(spot: R.Spot):
        if spot not in cache:
            cache[spot] = decision_policy(spot, view, tier, "icm", iters)
        return {d: FollowSpec(bp, v, e) for d, (v, e, bp) in cache[spot].items()}
    return policy


# The spots behind docs/research/data/2026-10-e1m-multiway.jsonl (BTN, SB, BB; blinds 50/100).
SPOTS = {"eq10": (1000, 1000, 1000), "eq15": (1500, 1500, 1500), "eq20": (2000, 2000, 2000),
         "short_btn": (500, 1500, 1500), "big_btn": (2500, 1000, 800), "short_bb": (1500, 1500, 500)}


def table(spots=SPOTS, payouts=(0.5, 0.3, 0.2), iters: int = 1500):
    """Rows of the research note's raw data: `python -m stalker.e1.multiway_pushfold` reproduces it."""
    for name, stacks in spots.items():
        spot = R.Spot(stacks, 50, 100, payouts)
        for vm in ("icm", "chipev"):
            nash = baseline(spot, vm, iters)
            for view in VIEWS:
                for tier in ("beginner", "mid", "pro"):
                    if view == "per_opp" and tier == "pro":
                        continue  # 101 x 101 codes: effectively no bottleneck
                    r = train(spot, view, tier, vm, iters, nash)
                    yield {"spot": name, "stacks": list(stacks), "vm": vm, "view": view, "tier": tier,
                           "expl": round(r.exploitability, 6), "nash": round(float(nash.sum()), 6),
                           "loss": round(r.loss, 6)}


if __name__ == "__main__":
    import json
    import sys

    for row in table(iters=int(sys.argv[1]) if len(sys.argv) > 1 else 1500):
        print(json.dumps(row), flush=True)
