"""Gate statistics: cluster bootstrap CI, SPRT, non-inferiority/superiority, sample size.

Conventions (referee/GATES.md "표본 정책"):
- A *cluster* is the unit that is resampled: one duplicate block (all seat-swapped games that
  share a game seed). Observations inside a cluster are correlated and never resampled alone.
- CIs are two-sided percentile intervals; gate decisions read the lower bound, so a 95% CI is
  a one-sided test at 2.5%.
- `sprt` is for futility stopping only: a gate may stop early when H0 is accepted, but success
  is declared only on the pre-registered sample size (`required_tournaments`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist
from typing import Sequence

import numpy as np

DEFAULT_BOOT = 4000


@dataclass(frozen=True)
class CI:
    mean: float
    lo: float
    hi: float
    n_clusters: int
    n_obs: int
    level: float


def bootstrap_ci(diffs: Sequence[float], cluster_ids: Sequence[object] | None = None, *,
                 level: float = 0.95, n_boot: int = DEFAULT_BOOT,
                 rng: np.random.Generator | None = None) -> CI:
    """Percentile CI of the mean of `diffs`, resampling whole clusters with replacement.

    `cluster_ids[i]` names the cluster of `diffs[i]` (None = every observation is its own
    cluster). The statistic is the pooled mean over all observations of the resampled clusters.
    """
    x = np.asarray(diffs, dtype=float)
    if x.ndim != 1 or len(x) < 2:
        raise ValueError(f"need a 1-D sequence of at least 2 diffs, got shape {x.shape}.")
    if not np.all(np.isfinite(x)):
        raise ValueError("diffs contain NaN/inf; drop or fix those games before computing a CI.")
    if not 0 < level < 1:
        raise ValueError(f"level={level}: must be in (0, 1).")
    ids = list(range(len(x))) if cluster_ids is None else list(cluster_ids)
    if len(ids) != len(x):
        raise ValueError(f"cluster_ids has {len(ids)} entries for {len(x)} diffs; pass one id per diff.")
    _, inv = np.unique(np.asarray([str(c) for c in ids]), return_inverse=True)
    k = int(inv.max()) + 1
    if k < 2:
        raise ValueError("all diffs are in one cluster; a cluster bootstrap needs at least 2 clusters.")
    sums = np.bincount(inv, weights=x, minlength=k)
    counts = np.bincount(inv, minlength=k).astype(float)
    rng = rng if rng is not None else np.random.default_rng(0)
    w = rng.multinomial(k, np.full(k, 1.0 / k), size=n_boot).astype(float)
    boot = (w @ sums) / (w @ counts)
    a = (1 - level) / 2
    lo, hi = np.quantile(boot, [a, 1 - a])
    return CI(float(x.mean()), float(lo), float(hi), k, len(x), level)


@dataclass(frozen=True)
class SPRTResult:
    decision: str  # "accept_h1" | "accept_h0" | "continue"
    n: int  # observations consumed when the decision was reached (all of them for "continue")
    llr: float
    lower: float  # log(beta / (1 - alpha))
    upper: float  # log((1 - beta) / alpha)


def sprt(observations: Sequence[float], delta0: float, delta1: float, sigma: float, *,
         alpha: float = 0.05, beta: float = 0.1) -> SPRTResult:
    """Wald SPRT for a normal mean, H0: mu = delta0 vs H1: mu = delta1, known `sigma`.

    Observations are consumed in order; the first boundary crossing decides. Use one observation
    per cluster (e.g. a duplicate block's mean diff) so they are independent.
    """
    if sigma <= 0 or not math.isfinite(sigma):
        raise ValueError(f"sigma={sigma}: must be a positive finite standard deviation.")
    if delta1 == delta0:
        raise ValueError("delta0 == delta1: the hypotheses must differ.")
    if not (0 < alpha < 1 and 0 < beta < 1):
        raise ValueError(f"alpha={alpha}, beta={beta}: both must be in (0, 1).")
    lower, upper = math.log(beta / (1 - alpha)), math.log((1 - beta) / alpha)
    step = (delta1 - delta0) / sigma ** 2
    mid = (delta0 + delta1) / 2
    llr = 0.0
    n = 0
    for n, x in enumerate(observations, 1):
        llr += step * (float(x) - mid)
        if llr >= upper:
            return SPRTResult("accept_h1", n, llr, lower, upper)
        if llr <= lower:
            return SPRTResult("accept_h0", n, llr, lower, upper)
    return SPRTResult("continue", n, llr, lower, upper)


@dataclass(frozen=True)
class Decision:
    passed: bool
    ci: CI
    threshold: float
    rule: str


def noninferiority(diffs: Sequence[float], cluster_ids: Sequence[object] | None = None, *,
                   delta_ni: float, level: float = 0.95, n_boot: int = DEFAULT_BOOT,
                   rng: np.random.Generator | None = None) -> Decision:
    """Pass when the CI lower bound of mean(candidate - baseline) is above -delta_ni."""
    if delta_ni < 0:
        raise ValueError(f"delta_ni={delta_ni}: give the margin as a non-negative number.")
    ci = bootstrap_ci(diffs, cluster_ids, level=level, n_boot=n_boot, rng=rng)
    return Decision(ci.lo > -delta_ni, ci, -delta_ni, "ci.lo > -delta_ni")


def superiority(diffs: Sequence[float], cluster_ids: Sequence[object] | None = None, *,
                delta_min: float = 0.0, level: float = 0.95, n_boot: int = DEFAULT_BOOT,
                rng: np.random.Generator | None = None) -> Decision:
    """Pass when the CI lower bound is > 0 and >= delta_min (GATES.md Gate A ②, Gate B/C)."""
    if delta_min < 0:
        raise ValueError(f"delta_min={delta_min}: the minimum practical effect must be >= 0.")
    ci = bootstrap_ci(diffs, cluster_ids, level=level, n_boot=n_boot, rng=rng)
    return Decision(ci.lo > 0 and ci.lo >= delta_min, ci, delta_min, "ci.lo > 0 and ci.lo >= delta_min")


def required_tournaments(sigma: float, delta: float, *, alpha: float = 0.05, power: float = 0.9) -> int:
    """Clusters needed so a two-sided (1-alpha) CI's lower bound clears 0 with prob. `power` at effect `delta`.

    `sigma` is the SD of one cluster's diff (measure it on the same duplicate scheme you will run).
    n = ((z_{1-alpha/2} + z_{power}) * sigma / delta)^2, rounded up.
    """
    if sigma <= 0 or delta <= 0:
        raise ValueError(f"sigma={sigma}, delta={delta}: both must be positive.")
    if not (0 < alpha < 1 and 0 < power < 1):
        raise ValueError(f"alpha={alpha}, power={power}: both must be in (0, 1).")
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return max(2, math.ceil((z * sigma / delta) ** 2))
