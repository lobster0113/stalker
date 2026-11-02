"""Variance control for the own-reach average-strategy weight, on three-handed Kuhn (#448).

`avg_rule="own"` (#426) adds sigma / prod(other non-traversers' reach) at a seat's node. That weight is unbiased
for the own-reach average but heavy-tailed (E3: median 22, max 7e7). Four estimators of the per-key average
strategy are compared against the own-reach truth (`exact_update`, avg_reach="own"), each from `steps` sampled passes
(every traverser once per pass, the strategy drifting, see `trajectory`), over `reps` independent replicates:

  none   plain own weight
  cap    weight clipped at c (the E3 weight is t / prod(reach), so a cap at c*t clips 1/prod at c)
  (self-normalised per key is not run: sum(w sigma) / sum(w) is sum(w sigma) / sum(w) and each sigma row sums to 1,
   so it equals the served policy of "none" exactly; the policy is always normalised per key.)
  exact  Pluribus-style reference: every m-th pass uses the exact increment times m instead of the sample

Metric: the key-visit-weighted mean L1 distance between the estimated and the true average policy (the policy is
what gets served), split into bias (distance of the replicate-mean policy from the truth) and sd (spread over
replicates). Leduc has two players here, where the divisor is empty and every estimator is the same, so it is not run.

    python -m stalker.vcfr.avg_variance     # local reference numbers, not CI
"""
from __future__ import annotations

import json
import sys

import numpy as np

from stalker.vcfr import toy as T

ESTIMATORS = ("none", "cap2", "cap8", "cap32", "exact")


def _policy(avg: T.Table) -> dict[str, np.ndarray]:
    return {k: v / v.sum() if v.sum() > 0 else np.full(len(v), 1 / len(v)) for k, v in avg.items()}


def trajectory(root, rng: np.random.Generator, steps: int, alpha: float, drift: float = 0.15) -> list[T.Table]:
    """A slowly drifting strategy sequence (a logit random walk from a skewed start), as training gives. The
    average then mixes different sigma_t. (With sigma frozen every increment is a multiple of sigma and the
    normalised policy is sigma whatever the weights are, so the weight cannot be compared on a frozen strategy.)"""
    info = T.keys(root)
    logit = {k: np.log(rng.dirichlet(np.full(a, alpha)) + 1e-9) for k, (_, a) in sorted(info.items())}
    out = []
    for _ in range(steps):
        logit = {k: v + drift * rng.standard_normal(len(v)) for k, v in logit.items()}
        out.append({k: np.exp(v - v.max()) / np.exp(v - v.max()).sum() for k, v in logit.items()})
    return out


def estimate(root, sigmas: list[T.Table], name: str, rng: np.random.Generator, exact: list[list[T.Table]],
             exact_every: int = 20) -> dict[str, np.ndarray]:
    """Per-key average policy over the passes t = 1..len(sigmas), linear averaging (increment x t), one estimator."""
    cap = {"cap2": 2.0, "cap8": 8.0, "cap32": 32.0}.get(name)
    s = T.E3Sampler(root, avg_rule="own", avg_cap=cap)
    total: T.Table = {}
    for t, sigma in enumerate(sigmas, 1):
        for p in range(3):
            if name == "exact":    # only every m-th pass adds to the average, exactly, times m
                avg = {k: v * exact_every for k, v in exact[t - 1][p].items()} if t % exact_every == 0 else {}
            else:
                avg = s.sample(sigma, p, rng)[1]
            for k, v in avg.items():
                T._acc(total, k, t * v)
    return _policy(total)


def study(steps: int = 100, reps: int = 30, seed: int = 1, alpha: float = 0.3) -> list[dict]:
    root = T.kuhn3()
    rng = np.random.default_rng(seed)
    sigmas = trajectory(root, rng, steps, alpha)
    exact = [[T.exact_update(root, T.identity, sg, p, 3, "own")[1] for p in range(3)] for sg in sigmas]
    truth_tot: T.Table = {}
    for t, per in enumerate(exact, 1):
        for a in per:
            for k, v in a.items():
                T._acc(truth_tot, k, t * v)
    truth = _policy(truth_tot)
    mass = {k: float(v.sum()) for k, v in truth_tot.items()}
    z = sum(mass.values())
    out = []
    for name in ESTIMATORS:
        runs = [estimate(root, sigmas, name, rng, exact) for _ in range(reps)]
        bias = err = 0.0
        for k, w in mass.items():
            mat = np.array([r.get(k, np.full(len(truth[k]), 1 / len(truth[k]))) for r in runs])
            bias += w / z * float(np.abs(mat.mean(0) - truth[k]).sum())
            err += w / z * float(np.abs(mat - truth[k]).sum(1).mean())
        out.append({"estimator": name, "steps": steps, "reps": reps, "bias_l1": round(bias, 4), "mean_err_l1": round(err, 4)})
    return out


def main() -> int:
    for steps in (100, 400):
        for row in study(steps=steps):
            print(json.dumps({"note": "local reference numbers, not CI", **row}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
