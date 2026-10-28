"""Gate F v0 (#281): follow robustness on E1 heads-up push/fold, error model 1 (synthetic).

A policy is `policy(seat, stack_bb, ante_bb) -> FollowSpec`: per-bin action probabilities, the TP
judgment value each hand reads (0-100, `hand.equity` or `hand.pct` on the policy's own scale) and the
bin edges on that value. The follower bot perceives `clip(value + error, 0, 100)` with a tier's
Gaussian error and plays the policy's action for the bin it perceives. E1 has no calculation items
(the action head reads the bin directly), so "recompute the calculation items" is the bin lookup.

Expected loss is exact: the bin a hand is perceived in has probability Phi((e_b - v)/sigma) -
Phi((e_{b-1} - v)/sigma), and clipping to 0-100 does not change it because every edge is inside
(0, 100). So no sampling error enters the gate. `sample_policy` draws the same follower with
AR(1)-correlated errors (rho) from a seeded Generator; in E1 each seat decides once per hand, so rho
changes the variance of a session, not the expected loss (a test checks the sampled mean against the
exact one). Correlation matters once an environment has several decisions per hand.

Measured per (stack, ante) spot, in bb/hand, both seats:
- nash_loss: the follower pair's loss against the Nash anchor's opponent, versus the best response to
  it (SB + BB). This is what a user following the policy gives up to an equilibrium opponent.
- exploitability: the follower pair's summed exact best-response gain (`pushfold.exploitability`).
- each also for the noiseless policy, and the difference (follower - noiseless).
Pass (GATES.md 1: the tier's follower beats the target persona field with 95% CI) needs personas,
which E1 does not have: the result is report-only and says so (`verdict`).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from typing import Callable

import numpy as np

from referee.anchors import pushfold as P

SIGMA = {"beginner": 20.0, "mid": 12.0, "pro": 6.0}   # GATES.md Gate F initial draft
SEATS = ("sb", "bb")
VERDICT = "report_only: E1 has no persona field; Gate F pass (follower beats target personas, 95% CI) is not judged"


@dataclass
class FollowSpec:
    bin_probs: np.ndarray   # per bin, shove (SB) or call (BB) probability
    values: np.ndarray      # per hand class, TP value 0-100 the hand reads
    edges: np.ndarray       # ascending bin edges on the value, len(bin_probs) - 1, all inside (0, 100)

    def bins(self, values: np.ndarray) -> np.ndarray:
        return np.searchsorted(self.edges, values, side="right")

    def probs(self) -> np.ndarray:
        """The noiseless policy, per hand class."""
        return self.bin_probs[self.bins(self.values)]


Policy = Callable[[str, float, float], FollowSpec]

_erf = np.vectorize(erf)


def bin_weights(spec: FollowSpec, sigma: float) -> np.ndarray:
    """(169, bins) probability that each hand is perceived in each bin under N(0, sigma) error."""
    if sigma == 0:
        return np.eye(len(spec.bin_probs))[spec.bins(spec.values)]
    if not ((spec.edges > 0) & (spec.edges < 100)).all():
        raise ValueError("edges must lie inside (0, 100) so clipping cannot move a perceived bin")
    z = (spec.edges[None, :] - spec.values[:, None]) / sigma
    cdf = 0.5 * (1 + _erf(z / sqrt(2)))
    cdf = np.hstack([np.zeros((len(spec.values), 1)), cdf, np.ones((len(spec.values), 1))])
    return np.diff(cdf, axis=1)


def follow(spec: FollowSpec, sigma: float) -> np.ndarray:
    """Expected per-class action probability of the follower bot (exact)."""
    return bin_weights(spec, sigma) @ spec.bin_probs


def sample_policy(spec: FollowSpec, sigma: float, rho: float, deals: np.ndarray,
                  rng: np.random.Generator) -> np.ndarray:
    """Per-class mean action probability over a session of `deals` (hand classes, in order), with
    errors e_t = rho e_{t-1} + sqrt(1 - rho^2) sigma z_t (one decision per deal)."""
    if not 0 <= rho < 1:
        raise ValueError("rho must be in [0, 1)")
    z = rng.standard_normal(len(deals)) * sigma
    err = np.empty(len(deals))
    prev = z[0]
    err[0] = prev
    k = sqrt(1 - rho * rho)
    for t in range(1, len(deals)):
        prev = rho * prev + k * z[t]
        err[t] = prev
    act = spec.bin_probs[spec.bins(np.clip(spec.values[deals] + err, 0, 100))]
    num = np.bincount(deals, act, 169)
    den = np.bincount(deals, minlength=169)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)


def nash_loss(stack: float, ante: float, push: np.ndarray, call: np.ndarray) -> tuple[float, float]:
    """(SB, BB) bb/hand lost against the Nash anchor's opponent, versus the best response to it."""
    n_push, n_call = P.strategy(stack, ante)
    p, sb_call, bb_gain = P._payoffs(stack, ante)
    pu, fo = P._sb_values(n_call, p, sb_call, ante)
    sb = float(np.maximum(pu, fo).sum() - (push * pu + (1 - push) * fo).sum())
    g = P._bb_gain(n_push, p, bb_gain)
    return sb, float(np.maximum(g, 0).sum() - (call * g).sum())


def evaluate(policy: Policy, spots, tier: str, sigma: float | None = None) -> dict:
    """Follower losses for one tier over (stack, ante) spots; sigma defaults to the tier's."""
    sigma = SIGMA[tier] if sigma is None else sigma
    rows = []
    for stack, ante in spots:
        sb, bb = policy("sb", stack, ante), policy("bb", stack, ante)
        base = (sb.probs(), bb.probs())
        fol = (follow(sb, sigma), follow(bb, sigma))
        nl0, nl1 = sum(nash_loss(stack, ante, *base)), sum(nash_loss(stack, ante, *fol))
        ex0, ex1 = P.exploitability(stack, ante, *base), P.exploitability(stack, ante, *fol)
        rows.append({"stack": stack, "ante": ante, "nash_loss": round(nl1, 5), "nash_loss_noiseless": round(nl0, 5),
                     "nash_loss_added": round(nl1 - nl0, 5), "exploitability": round(ex1, 5),
                     "exploitability_noiseless": round(ex0, 5), "exploitability_added": round(ex1 - ex0, 5)})
    mean = {k: round(float(np.mean([r[k] for r in rows])), 5) for k in rows[0] if k not in ("stack", "ante")}
    return {"tier": tier, "sigma": sigma, "spots": len(rows), "mean": mean, "rows": rows, "verdict": VERDICT}
