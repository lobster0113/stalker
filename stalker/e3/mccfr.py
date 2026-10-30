"""E3-1: external-sampling MCCFR for N-handed play with TP-keyed infosets and public ranges (#196).

Each iteration deals one hand and, for every seat in turn as the traverser, walks the tree exploring
all of the traverser's actions and sampling everyone else's from the current strategy (Lanctot et
al. 2009). Infosets are TP keys (stalker/e3/tp_key.py), so situations reached by different
histories share a strategy. Every seat's public range rides along the walk and is updated with
that seat's strategy per combo, which is what the equity step is measured against.

Keying by TP features breaks perfect recall, so CFR's convergence guarantee does not hold here; the
cost of that approximation is measured on exactly solvable sub-games (#192 §5).

How the average strategy is accumulated is an option (#426). Both rules add sigma at a seat's node during
the other seats' traversals. `avg_rule="legacy"` (the default, every run before #426) adds it as is: the
visit is reached with the chance, own and every other non-traverser's reach, so from three players on the
other opponents' reach weights the average too (#414 oracle). `avg_rule="own"` divides the increment by
the sigma product of the other non-traversers' sampled actions above the node, so in expectation it is
weighted by chance and own reach only. Heads-up there is nobody to divide out and the two are bit-identical.

    python -m stalker.e3.mccfr --tier beginner --iters 50 --seed 1
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict

import numpy as np

from stalker.e3 import game as G
from stalker.e3 import tp_key as K

AVG_RULES = ("legacy", "own")

class E3MCCFR:
    def __init__(self, seed: int = 0, k: int = 5, n: int = 6, depth: str = "full", menu: str = "v1",
                 raise_cap: int | None = G.RAISE_CAP, avg_rule: str = "legacy"):
        if avg_rule not in AVG_RULES:
            raise ValueError(f"avg_rule must be one of {AVG_RULES}, got {avg_rule!r}")
        self.avg_rule = avg_rule
        self.rng = np.random.default_rng(seed)
        self.k, self.n, self.depth = k, n, depth
        self.menu, self.raise_cap = menu, raise_cap   # game rules (#339); v1 + cap 3 is every earlier run
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
        if steps.max() >= self.k:  # pro heads-up postflop: steps carry board.nut (tp_key.NUT_BASE)
            out = np.zeros((len(steps), m))
            for v in np.unique(steps[steps >= 0]):
                out[steps == v] = self._sigma(K.key(public, int(v)), m)
            return out
        table = np.array([self._sigma(K.key(public, v), m) for v in range(self.k)])
        out = table[np.maximum(steps, 0)]
        out[steps < 0] = 0.0
        return out

    def iterate(self, iters: int = 1) -> None:
        for _ in range(iters):
            self.iterations += 1
            s = G.deal(self.rng, self.n, self.menu, self.raise_cap)
            for trav in range(self.n):
                self._walk(s, K.initial_ranges(self.n), trav, [1.0] * self.n)

    def _walk(self, s: G.State, ranges: list[np.ndarray], trav: int, reach: list[float]) -> float:
        # reach[m]: the sigma product of seat m's sampled actions above this node (read by avg_rule "own")
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
            return G.apply(s, acts[i]), K.update_range(ranges, p, probs[:, i])

        if p == trav:
            vals = np.array([self._walk(*child(i), trav, reach) for i in range(len(acts))])
            v = float(sigma @ vals)
            reg = self.regret.setdefault(key, np.zeros(len(acts)))
            np.maximum(reg + (vals - v), 0, out=reg)
            self.visits[key] += 1
            return v
        i = int(self.rng.choice(len(acts), p=sigma))
        avg = self.avg[key]
        if self.avg_rule == "legacy":
            self.avg[key] = (avg if avg is not None else 0) + self.iterations * sigma
            return self._walk(*child(i), trav, reach)
        w = self.iterations / math.prod(r for m, r in enumerate(reach) if m != p and m != trav)
        self.avg[key] = (avg if avg is not None else 0) + w * sigma
        nxt = reach.copy()
        nxt[p] *= float(sigma[i])
        return self._walk(*child(i), trav, nxt)

    def state(self) -> dict:
        """Everything `iterate` reads, as JSON data; `from_state` continues bit for bit (#301), so a run
        longer than one CI job (300 min) is chained from checkpoints."""
        # version 3 (#426): code that predates avg_rule would resume an "own" checkpoint as legacy, so it must refuse it
        return {"version": 3 if self.avg_rule == "own" else 1, "avg_rule": self.avg_rule,
                "k": self.k, "n": self.n, "depth": self.depth, "iterations": self.iterations,
                "nodes": self.nodes, "menu": self.menu, "raise_cap": self.raise_cap, "rng": self.rng.bit_generator.state,
                "regret": {k: v.tolist() for k, v in self.regret.items()},
                "avg": {k: v.tolist() for k, v in self.avg.items() if v is not None}, "visits": dict(self.visits),
                **self._grid()}

    def _grid(self) -> dict:
        # The pro table's board.nut grid is part of its key meaning (#332): 17 -> 5 steps changed `n<nut>`.
        return {"nut_k": K.NUT_K} if self.depth == "pro" else {}

    @classmethod
    def from_state(cls, st: dict, avg_rule: str | None = None) -> "E3MCCFR":
        """`avg_rule`, if given, is the rule the caller means to continue with; a checkpoint of the other is refused."""
        if st.get("version") not in (1, 3):
            raise ValueError(f"checkpoint version {st.get('version')!r}; this code reads versions 1 and 3")
        rule = st.get("avg_rule", "legacy")    # checkpoints before #426 are all legacy
        if (rule == "own") != (st["version"] == 3):
            raise ValueError(f"checkpoint version {st['version']} with avg_rule {rule!r}: an avg_rule 'own' "
                             "checkpoint is version 3, a legacy one version 1")
        if avg_rule is not None and avg_rule != rule:
            raise ValueError(f"checkpoint average strategy was accumulated with avg_rule {rule!r}, not {avg_rule!r} "
                             "(#426); the two rules must not mix in one average - resume it with its own rule "
                             "or start a fresh run")
        if st["depth"] == "pro" and st.get("nut_k", K.K_PRO) != K.NUT_K:
            raise ValueError(f"checkpoint board.nut has {st.get('nut_k', K.K_PRO)} steps; this code uses {K.NUT_K} "
                             "(#332) - start a fresh run instead of resuming it")
        m = cls(0, st["k"], st["n"], st["depth"], st.get("menu", "v1"), st.get("raise_cap", G.RAISE_CAP), rule)
        m.rng.bit_generator.state = st["rng"]
        m.iterations, m.nodes = st["iterations"], st["nodes"]
        m.regret = {k: np.array(v, dtype=float) for k, v in st["regret"].items()}
        m.avg.update({k: np.array(v, dtype=float) for k, v in st["avg"].items()})
        m.visits.update(st["visits"])
        return m

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
    ap.add_argument("--menu", choices=G.MENUS, default="v1")
    ap.add_argument("--no-raise-cap", action="store_true")
    ap.add_argument("--avg-rule", choices=AVG_RULES, default="legacy")
    a = ap.parse_args(argv)
    m = E3MCCFR(a.seed, K.TIER_K[a.tier], a.players, K.TIER_DEPTH[a.tier], a.menu,
                None if a.no_raise_cap else G.RAISE_CAP, a.avg_rule)
    t0 = time.monotonic()
    m.iterate(a.iters)
    dt = time.monotonic() - t0
    print(json.dumps({"tier": a.tier, "players": a.players, "iters": a.iters, "seconds": round(dt, 1),
                      "iters_per_s": round(a.iters / dt, 3), "nodes_per_iter": round(m.nodes / a.iters, 1),
                      "keys": len(m.regret), "menu": m.menu, "raise_cap": m.raise_cap,
                      # the bound counts the v1 legal-action sets only
                      "theoretical_keys": K.theoretical_keys(a.players, m.k, m.depth) if m.menu == "v1" else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
