"""External-sampling MCCFR for E2 (unconstrained baseline, ADR 0012).

Self-play: each iteration deals one hand, and for each player in turn walks the tree sampling the
opponent's actions from the current strategy while exploring all of the traverser's actions
(Lanctot et al. 2009). Infoset = (player, street, card bucket, public history). Regret matching+
with linear averaging. Deterministic for a seed.

    python -m stalker.e2.mccfr --iters 2000 --seed 1 --out runs/e2.json
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from stalker.e2 import game as G
from stalker.e2.abstraction import bucket


def infoset(s: G.State) -> str:
    p = s.to_act
    return f"{p}|{s.street}|{bucket(s.hole[p], s.board)}|{''.join(h if len(h) == 1 else h[1:] for h in s.history)}"


class MCCFR:
    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)
        self.regret: dict[str, np.ndarray] = {}
        self.avg: dict[str, np.ndarray] = defaultdict(lambda: None)
        self.iterations = 0

    def _sigma(self, key: str, n: int) -> np.ndarray:
        r = self.regret.get(key)
        if r is None:
            return np.full(n, 1.0 / n)
        pos = np.maximum(r, 0)
        s = pos.sum()
        return pos / s if s > 0 else np.full(n, 1.0 / n)

    def _walk(self, s: G.State, trav: int) -> float:
        if s.done:
            v = G.payoff(s) / G.BB
            return v if trav == 0 else -v
        acts = G.legal(s)
        key = infoset(s)
        sigma = self._sigma(key, len(acts))
        if s.to_act == trav:
            vals = np.array([self._walk(G.apply(s, a), trav) for a in acts])
            v = float(sigma @ vals)
            r = self.regret.setdefault(key, np.zeros(len(acts)))
            np.maximum(r + (vals - v), 0, out=r)
            return v
        a = self.rng.choice(len(acts), p=sigma)
        avg = self.avg[key]
        self.avg[key] = (avg if avg is not None else 0) + self.iterations * sigma
        return self._walk(G.apply(s, acts[a]), trav)

    def iterate(self, n: int = 1) -> None:
        for _ in range(n):
            self.iterations += 1
            s = G.deal(self.rng)
            for trav in (0, 1):
                self._walk(s, trav)

    def policy(self) -> dict[str, list[float]]:
        out = {}
        for k, v in self.avg.items():
            if v is not None and v.sum() > 0:
                out[k] = (v / v.sum()).tolist()
        return out


def strategy_fn(policy: dict[str, list[float]]):
    """Callable (state) -> action probabilities over legal(state); uniform where the policy is silent."""
    def f(s: G.State) -> np.ndarray:
        acts = G.legal(s)
        p = policy.get(infoset(s))
        return np.asarray(p) if p is not None and len(p) == len(acts) else np.full(len(acts), 1.0 / len(acts))
    return f


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="E2 external-sampling MCCFR (local reference numbers)")
    ap.add_argument("--iters", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    m = MCCFR(a.seed)
    m.iterate(a.iters)
    dt = time.monotonic() - t0
    pol = m.policy()
    print(json.dumps({"iters": a.iters, "seed": a.seed, "seconds": round(dt, 2), "iters_per_s": round(a.iters / dt, 1),
                      "infosets": len(m.regret)}))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"seed": a.seed, "iters": a.iters, "policy": pol}), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
