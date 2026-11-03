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

Metrics: the key-visit-weighted mean L1 distance between an estimated and the true average policy (the policy is
what gets served). `mean_err_l1` is the mean over replicates (bias and sampling noise together). `bias_l1` has no
sampling noise: it is the distance of the policy built from the *exact expectation* of the estimator's increments
(`expected_increment` enumerates every sampled path of the 24-deal tree), i.e. the asymptotic bias as reps -> inf.
(A replicate-mean policy would keep an err/sqrt(reps) noise floor and could not show a bias this small, #448 review.)
Leduc has two players here, where the divisor is empty and every estimator is the same, so it is not run.

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


def expected_increment(root, sigma: T.Table, p: int, cap: float | None) -> T.Table:
    """Exact E[avg increment] of `E3Sampler(avg_rule="own", avg_cap=cap).sample(sigma, p, .)`, by enumerating the
    sampled paths (probability-weighted). With cap=None it equals `exact_update(..., "own")[1]`."""
    out: T.Table = {}

    def walk(n, pr: float, reach: dict[int, float]) -> None:
        if n.kind == T.TERMINAL:
            return
        probs = np.asarray(n.probs) if n.kind == T.CHANCE else sigma[T.identity(n.infoset)]
        if n.kind != T.CHANCE and n.player == p:
            for c in n.children:
                walk(c, pr, reach)
            return
        if n.kind != T.CHANCE:
            me = n.player
            inv = 1 / np.prod([r for m, r in reach.items() if m != me])
            T._acc(out, T.identity(n.infoset), pr * (inv if cap is None else min(inv, cap)) * probs)
        for i, c in enumerate(n.children):
            nxt = reach if n.kind == T.CHANCE else {**reach, n.player: reach.get(n.player, 1.0) * probs[i]}
            walk(c, pr * probs[i], nxt)

    walk(root, 1.0, {})
    return out


def expected_policy(root, sigmas: list[T.Table], cap: float | None) -> dict[str, np.ndarray]:
    total: T.Table = {}
    for t, sigma in enumerate(sigmas, 1):
        for p in range(3):
            for k, v in expected_increment(root, sigma, p, cap).items():
                T._acc(total, k, t * v)
    return _policy(total)


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
        # exact is deterministic (its error is its bias); the sampled ones have their expectation enumerated
        ref = (runs[0] if name == "exact"
               else expected_policy(root, sigmas, {"cap2": 2.0, "cap8": 8.0, "cap32": 32.0}.get(name)))
        bias = err = 0.0
        for k, w in mass.items():
            mat = np.array([r.get(k, np.full(len(truth[k]), 1 / len(truth[k]))) for r in runs])
            bias += w / z * float(np.abs(ref.get(k, np.full(len(truth[k]), 1 / len(truth[k]))) - truth[k]).sum())
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
