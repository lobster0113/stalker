"""TP bottleneck policies for E1 heads-up push/fold, trained by self-play and judged exactly.

Environment (the existing anchor, `referee.anchors.pushfold`): chip EV, SB shoves or folds, BB
calls or folds, stacks 1-15bb, BB ante 0 or 1bb, 169 hand classes with exact card removal.

Bottleneck: neither seat sees its cards, only the TP item `hand.equity` quantized to a tier's scale
(beginner 0/25/50/75/100, mid steps of 10, pro steps of 1) plus the DecisionContext (stack, ante).
- SB: equity against a random hand (BB has not acted; `opp.range` = everything).
- BB: equity against the SB's shoving range, i.e. `opp.range` under the assumed SB policy. In
  self-play that assumption is the SB's current strategy, so the BB's equity scale moves as the SB
  learns.

Training is fictitious play between the two bottleneck policies: each round both best-respond (in
bucket space) to the other's running average, so bluff-shoves, exploits and counter-exploits are
explored and averaged out. The BB's buckets are recomputed every
iteration from the SB's current average range, and the BB's average is projected onto the final
buckets so the delivered policy is a function of its TP value. The result is measured with the exact 169-class best
response (`pushfold.exploitability`), never with the bucketed game.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from referee.anchors import pushfold as P

TIER_STEP = {"beginner": 25, "mid": 10, "pro": 1}
E1_STACKS = [s for s in P.STACKS if s <= 15]
E1_ANTES = P.ANTES


def _quantize(equity_pct: np.ndarray, step: int) -> np.ndarray:
    return np.rint(equity_pct / step).astype(int)


def sb_equity() -> np.ndarray:
    """Equity (%) of each class against a random non-conflicting hand."""
    e, p = P._tables()
    return 100.0 * (p * e).sum(axis=1) / p.sum(axis=1)


def sb_equity_when_called(call: np.ndarray) -> np.ndarray:
    """Equity (%) of each SB class against the BB's calling range `call` (card removal exact)."""
    e, p = P._tables()
    w = p * call[None, :]
    tot = w.sum(axis=1)
    return 100.0 * np.where(tot > 0, (w * e).sum(axis=1) / np.where(tot > 0, tot, 1.0), 0.5)


def bb_equity(push: np.ndarray) -> np.ndarray:
    """Equity (%) of each BB class against the SB's shoving range `push` (card removal exact)."""
    e, p = P._tables()
    w = p * push[:, None]
    tot = w.sum(axis=0)
    eq = (w * (1.0 - e)).sum(axis=0) / np.where(tot > 0, tot, 1.0)
    return 100.0 * np.where(tot > 0, eq, 0.5)


@dataclass
class Result:
    stack: float
    ante: float
    tier: str
    push: np.ndarray            # per class, SB shove probability (a function of the SB bucket)
    call: np.ndarray            # per class, BB call probability (a function of the BB bucket)
    exploitability: float       # exact, summed BR gain of both seats, bb/hand
    nash_exploitability: float  # the unconstrained fictitious-play solution's, same measure
    bucket_changes: int         # iterations where the BB's equity bucketing moved
    consistent: bool = True     # both delivered policies are functions of buckets computed from the other


def _is_function_of(values: np.ndarray, buckets: np.ndarray) -> bool:
    """True if values are constant within every bucket (the policy reads only its TP value)."""
    return all(np.ptp(values[buckets == b]) < 1e-12 for b in np.unique(buckets))


def _project(values: np.ndarray, buckets: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Make a per-class policy a function of the bucket: reach-weighted mean within each bucket."""
    n = buckets.max() + 1
    num = np.bincount(buckets, values * weight, n)
    den = np.bincount(buckets, weight, n)
    return (num / np.where(den > 0, den, 1.0))[buckets]


def seat_gains(stack: float, ante: float, push: np.ndarray, call: np.ndarray) -> tuple[float, float]:
    """(SB, BB) best-response gains, bb/hand; their sum is `pushfold.exploitability`."""
    p, sb_call, bb_gain = P._payoffs(stack, ante)
    pu, fo = P._sb_values(call, p, sb_call, ante)
    sb = float(np.maximum(pu, fo).sum() - (push * pu + (1 - push) * fo).sum())
    g = P._bb_gain(push, p, bb_gain)
    return sb, float(np.maximum(g, 0).sum() - (call * g).sum())


def train(stack: float, ante: float, tier: str, iters: int = 4000, sb_view: str = "random") -> Result:
    """sb_view: what the SB's `hand.equity` is measured against — "random" (TP v0.1: the BB's range
    before it acts) or "called" (the BB's calling range, i.e. equity when called)."""
    step = TIER_STEP[tier]
    p, sb_call, bb_gain = P._payoffs(stack, ante)
    sb_b = _quantize(sb_equity(), step)
    push = np.full(169, 0.5)          # SB running average, per class
    call = np.full(169, 0.5)          # BB running average, per class
    changes = 0
    bb_b = _quantize(bb_equity(push), step)
    for t in range(1, iters + 1):
        if sb_view == "called":
            sb_b = _quantize(sb_equity_when_called(call), step)
        nb_sb = sb_b.max() + 1
        s = _project(push, sb_b, p.sum(axis=1))
        # The BB's equity scale is equity against the SB's current (average) range: recompute it.
        new_bb = _quantize(bb_equity(s), step)
        changes += int(not np.array_equal(new_bb, bb_b))
        bb_b = new_bb
        nb_bb = bb_b.max() + 1
        c_bucket = _project(call, bb_b, p.sum(axis=0))
        pu, fo = P._sb_values(c_bucket, p, sb_call, ante)
        s_br = (np.bincount(sb_b, pu, nb_sb) > np.bincount(sb_b, fo, nb_sb)).astype(float)[sb_b]
        g = P._bb_gain(s, p, bb_gain)
        c_br = (np.bincount(bb_b, g, nb_bb) > 0).astype(float)[bb_b]
        push += (s_br - push) / (t + 1)
        call += (c_br - call) / (t + 1)
    # Deliver policies that are functions of their own TP values, each measured against the other
    # delivered policy (the assumption a user would be taught). Usually a few passes reach a fixed
    # point; with sb_view="called" the two bucketings can cycle, and then no consistent pair is
    # delivered: the result is marked consistent=False and shown as such in the table (#268 review).
    avg_push, avg_call = push, call
    for _ in range(50):
        if sb_view == "called":
            sb_b = _quantize(sb_equity_when_called(call), step)
        push = _project(avg_push, sb_b, p.sum(axis=1))
        bb_b = _quantize(bb_equity(push), step)
        new_call = _project(avg_call, bb_b, (p * push[:, None]).sum(axis=0))
        if np.array_equal(new_call, call):
            break
        call = new_call
    sb_final = _quantize(sb_equity_when_called(call), step) if sb_view == "called" else sb_b
    consistent = _is_function_of(push, sb_final) and _is_function_of(call, _quantize(bb_equity(push), step))
    _, _, nash_ex = P.solve(stack, ante, max_iter=iters)
    return Result(stack, ante, tier, push, call, P.exploitability(stack, ante, push, call), nash_ex, changes,
                  consistent)


def table(stacks=None, antes=None, tiers=("beginner", "mid", "pro"), views=("random", "called"),
          iters: int = 4000) -> list[dict]:
    rows = []
    for ante in antes or E1_ANTES:
        for stack in stacks or E1_STACKS:
            for view in views:
                for tier in tiers:
                    r = train(stack, ante, tier, iters, view)
                    sb_gain, bb_gain = seat_gains(stack, ante, r.push, r.call)
                    sb_freq, bb_freq = P.frequencies(r.push, r.call)
                    rows.append({"stack": stack, "ante": ante, "sb_view": view, "tier": tier,
                                 "exploitability": round(r.exploitability, 5), "sb_gain": round(sb_gain, 5),
                                 "bb_gain": round(bb_gain, 5), "nash_fp_exploitability": round(r.nash_exploitability, 5),
                                 "sb_shove": round(sb_freq, 4), "bb_call": round(bb_freq, 4),
                                 "consistent": r.consistent})
    return rows


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="E1 TP bottleneck exploitability table (local reference numbers)")
    ap.add_argument("--stacks", type=float, nargs="*")
    ap.add_argument("--antes", type=float, nargs="*")
    ap.add_argument("--iters", type=int, default=4000)
    a = ap.parse_args()
    for row in table(a.stacks, a.antes, iters=a.iters):
        print(json.dumps(row), flush=True)
