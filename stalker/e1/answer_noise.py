"""Which TP question form tolerates human estimation error better? (#216, Gate T simulation)

Two forms of the `hand.equity` item, each taught as a policy over its tier's buckets (E1 push/fold):
- "equity" (form A): "how often do I win against their range?" on the tier's equal-width scale
  (`tp_pushfold` scale "uniform").
- "rank" (form B): "what top-% of my range is this hand?" on equal-mass buckets (scale "quantile").

A simulated learner knows the bucket policy perfectly but estimates the TP value with error:
estimate = v + shrink * (50 - v) + N(0, sigma), in the form's own percentage points (`shrink` is an
anchoring pull toward the middle of the scale). The estimate picks a bucket, the bucket's action is
played. The loss is computed exactly, without sampling: each class plays the mixture of bucket
actions weighted by the Gaussian probability of landing in each bucket, and the resulting pair of
policies is measured with the exact 169-class best response.

Whether a percentage point of equity error equals a point of rank error for real people is the open
question; this table gives the loss curves per form so the Gate E measurement (real answer errors)
only has to supply the two sigmas.
"""
from __future__ import annotations

from math import erf, sqrt

import numpy as np

from referee.anchors import pushfold as P
from stalker.e1 import tp_pushfold as T

FORMS = {"equity": "uniform", "rank": "quantile"}


def _phi(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(erf)(x / sqrt(2.0)))


def percentile(value: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Weighted mid-rank of each class, 0-100: the `hand.pct` answer `_quantile_bins` buckets."""
    order = np.argsort(value, kind="stable")
    w = weight[order] / weight.sum()
    out = np.empty(len(order))
    out[order] = 100.0 * (np.cumsum(w) - w / 2)
    return out


def edges(form: str, tier: str) -> np.ndarray:
    """Inner bucket boundaries on the 0-100 answer scale (bucket b is between edges b-1 and b)."""
    if form == "equity":
        step = T.TIER_STEP[tier]
        return np.arange(step / 2, 100, step, dtype=float)  # nearest-step rounding, as `_quantize`
    levels = T.TIER_LEVELS[tier]
    return 100.0 * np.arange(1, levels) / levels


def bucket_probs(value: np.ndarray, cuts: np.ndarray, sigma: float, shrink: float = 0.0) -> np.ndarray:
    """(classes, buckets) probability that a learner with this error answers into each bucket."""
    mean = value + shrink * (50.0 - value)
    if sigma <= 0:
        b = np.searchsorted(cuts, mean, side="right")
        out = np.zeros((len(value), len(cuts) + 1))
        out[np.arange(len(value)), b] = 1.0
        return out
    cdf = _phi((cuts[None, :] - mean[:, None]) / sigma)
    cdf = np.concatenate([np.zeros((len(value), 1)), cdf, np.ones((len(value), 1))], axis=1)
    return np.diff(cdf, axis=1)


def bucket_actions(policy: np.ndarray, value: np.ndarray, cuts: np.ndarray) -> np.ndarray:
    """Action per bucket of a policy that is a function of the bucket. A bucket no class falls in
    (an equity range nobody holds) takes its nearest occupied bucket's action: the taught table has
    no row there, so the learner reads the closest one."""
    b = np.searchsorted(cuts, value, side="right")
    n = len(cuts) + 1
    act = np.full(n, np.nan)
    for k in np.unique(b):
        act[k] = policy[b == k].mean()
    occ = np.flatnonzero(~np.isnan(act))
    for k in np.flatnonzero(np.isnan(act)):
        act[k] = act[occ[np.argmin(np.abs(occ - k))]]
    return act


def values(form: str, push: np.ndarray, p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """True answers (SB, BB) per class on the form's 0-100 scale, against the taught SB range."""
    sb, bb = T.sb_equity(), T.bb_equity(push)
    if form == "rank":
        sb, bb = percentile(sb, p.sum(axis=1)), percentile(bb, p.sum(axis=0))
    return sb, bb


def noisy_loss(r: T.Result, form: str, sigma: float, shrink: float = 0.0) -> float:
    """Exact exploitability (bb/hand) of the taught policy `r` played by a learner with answer error."""
    p, _, _ = P._payoffs(r.stack, r.ante)
    cuts = edges(form, r.tier)
    sb_v, bb_v = values(form, r.push, p)
    push = bucket_probs(sb_v, cuts, sigma, shrink) @ bucket_actions(r.push, sb_v, cuts)
    call = bucket_probs(bb_v, cuts, sigma, shrink) @ bucket_actions(r.call, bb_v, cuts)
    return P.exploitability(r.stack, r.ante, push, call)


# The grid behind docs/research/data/2026-10-tp-form-noise.jsonl (#261 review: defaults must regenerate it).
SIGMAS = (0, 1, 2, 3, 5, 7.5, 10, 15, 20, 30)
SHRINKS = (0.0, 0.2)


def table(stacks=None, antes=None, tiers=("beginner", "mid"), sigmas=SIGMAS,
          shrinks=SHRINKS, iters: int = 4000) -> list[dict]:
    rows = []
    for ante in antes or T.E1_ANTES:
        for stack in stacks or T.E1_STACKS:
            for tier in tiers:
                for form, scale in FORMS.items():
                    r = T.train(stack, ante, tier, iters, "random", scale)
                    for shrink in shrinks:
                        for sigma in sigmas:
                            rows.append({"stack": stack, "ante": ante, "tier": tier, "form": form,
                                         "sigma": sigma, "shrink": shrink,
                                         "loss": round(noisy_loss(r, form, sigma, shrink), 5)})
    return rows


def summary(rows: list[dict]) -> list[dict]:
    """Mean loss over the stack x ante grid per (tier, form, shrink, sigma)."""
    keys = sorted({(r["tier"], r["form"], r["shrink"], r["sigma"]) for r in rows})
    return [{"tier": t, "form": f, "shrink": s, "sigma": g,
             "mean_loss": round(float(np.mean([r["loss"] for r in rows if (r["tier"], r["form"], r["shrink"], r["sigma"]) == (t, f, s, g)])), 4)}
            for t, f, s, g in keys]


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="E1 TP question-form noise table (#216, local reference numbers)")
    ap.add_argument("--stacks", type=float, nargs="*")
    ap.add_argument("--antes", type=float, nargs="*")
    ap.add_argument("--iters", type=int, default=4000)
    num = lambda x: int(float(x)) if float(x).is_integer() else float(x)  # 5 stays 5, as in the committed jsonl
    ap.add_argument("--sigmas", type=num, nargs="+", default=list(SIGMAS))
    ap.add_argument("--shrinks", type=float, nargs="+", default=list(SHRINKS))
    ap.add_argument("--summary", action="store_true", help="print grid means instead of every row")
    a = ap.parse_args()
    out = table(a.stacks, a.antes, sigmas=a.sigmas, shrinks=a.shrinks, iters=a.iters)
    for row in summary(out) if a.summary else out:
        print(json.dumps(row), flush=True)
