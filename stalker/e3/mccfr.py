"""E3-1: external-sampling MCCFR for N-handed play with TP-keyed infosets and public ranges (#196).

Each iteration deals one hand and, for every seat in turn as the traverser, walks the tree exploring
all of the traverser's actions and sampling everyone else's from the current strategy (Lanctot et
al. 2009). Infosets are TP keys (stalker/e3/tp_key.py), so situations reached by different
histories share a strategy. Every seat's public range rides along the walk and is updated with
that seat's strategy per combo, which is what the equity step is measured against.

Keying by TP features breaks perfect recall, so CFR's convergence guarantee does not hold here; the
cost of that approximation is measured on exactly solvable sub-games (#192 §5).

    python -m stalker.e3.mccfr --tier beginner --iters 50 --seed 1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict

import numpy as np

from stalker.e3 import game as G
from stalker.e3 import tp_key as K


class E3MCCFR:
    def __init__(self, seed: int = 0, k: int = 5, n: int = 6, depth: str = "full"):
        self.rng = np.random.default_rng(seed)
        self.k, self.n, self.depth = k, n, depth
        self.regret: dict[str, np.ndarray] = {}
        self.avg: dict[str, np.ndarray] = defaultdict(lambda: None)
        self.iterations = 0
        self.nodes = 0
        self.visits: dict[str, int] = defaultdict(int)  # traverser updates per key (coverage diagnostics)

    def _sigma(self, key: str, m: int) -> np.ndarray:
        r = self.regret.get(key)
        if r is None:
            return np.full(m, 1.0 / m)
        pos = np.maximum(r, 0)
        t = pos.sum()
        return pos / t if t > 0 else np.full(m, 1.0 / m)

    def _seat_probs(self, public: str, steps: np.ndarray, m: int) -> np.ndarray:
        # One strategy row per equity step, gathered per combo; board collisions (-1) get zeros.
        table = np.array([self._sigma(K.key(public, v), m) for v in range(self.k)])
        out = table[np.maximum(steps, 0)]
        out[steps < 0] = 0.0
        return out

    def iterate(self, iters: int = 1) -> None:
        for _ in range(iters):
            self.iterations += 1
            s = G.deal(self.rng, self.n)
            for trav in range(self.n):
                self._walk(s, K.initial_ranges(self.n), trav)

    def _walk(self, s: G.State, ranges: list[np.ndarray], trav: int) -> float:
        if s.done:
            return float(G.payoff(s)[trav]) / G.BB
        self.nodes += 1
        acts = G.legal(s)
        p = s.to_act
        steps = K.equity_steps(s, p, ranges, self.k)
        public = K.public_key(s, p, self.depth)
        key = K.key(public, K.my_step(steps, s, p))
        sigma = self._sigma(key, len(acts))
        probs = self._seat_probs(public, steps, len(acts))

        def child(i: int):
            r = list(ranges)
            r[p] = ranges[p] * probs[:, i]
            return G.apply(s, acts[i]), r

        if p == trav:
            vals = np.array([self._walk(*child(i), trav) for i in range(len(acts))])
            v = float(sigma @ vals)
            reg = self.regret.setdefault(key, np.zeros(len(acts)))
            np.maximum(reg + (vals - v), 0, out=reg)
            self.visits[key] += 1
            return v
        i = int(self.rng.choice(len(acts), p=sigma))
        avg = self.avg[key]
        self.avg[key] = (avg if avg is not None else 0) + self.iterations * sigma
        return self._walk(*child(i), trav)

    def policy(self) -> dict[str, list[float]]:
        return {k: (v / v.sum()).tolist() for k, v in self.avg.items() if v is not None and v.sum() > 0}

    def current_policy(self) -> dict[str, list[float]]:
        """The regret-matching strategy of the last iteration (no early-iteration residue in it)."""
        return {k: self._sigma(k, len(r)).tolist() for k, r in self.regret.items()}


def coverage(m: E3MCCFR, by: int = -2) -> dict[str, dict[str, float]]:
    """Per value of one key field (default: the legal-action set), how many keys and how many had
    fewer than 10 traverser updates — where the table is still close to its uniform start."""
    out: dict[str, dict[str, float]] = {}
    for k, v in m.visits.items():
        f = k.split("|")[by]
        d = out.setdefault(f, {"keys": 0, "under10": 0})
        d["keys"] += 1
        d["under10"] += v < 10
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E3 TP-keyed MCCFR (local reference numbers)")
    ap.add_argument("--tier", choices=sorted(K.TIER_K), default="beginner")
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--players", type=int, default=6)
    a = ap.parse_args(argv)
    m = E3MCCFR(a.seed, K.TIER_K[a.tier], a.players, K.TIER_DEPTH[a.tier])
    t0 = time.monotonic()
    m.iterate(a.iters)
    dt = time.monotonic() - t0
    print(json.dumps({"tier": a.tier, "players": a.players, "iters": a.iters, "seconds": round(dt, 1),
                      "iters_per_s": round(a.iters / dt, 3), "nodes_per_iter": round(m.nodes / a.iters, 1),
                      "keys": len(m.regret), "theoretical_keys": K.theoretical_keys(a.players, m.k)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
