"""E3-1: external-sampling MCCFR for N-handed play with TP-keyed infosets and public ranges (#196).

Each iteration deals one hand and, for every seat in turn as the traverser, walks the tree exploring
all of the traverser's actions and sampling everyone else's from the current strategy (Lanctot et
al. 2009). Infosets are TP keys (stalker/e3/tp_key.py), so situations reached by different
histories share a strategy. Every seat's public range rides along the walk and is updated with
that seat's strategy per combo, which is what the equity step is measured against.

Which strategy moves those ranges is an option (#405). `ranges="current"` (the default, every run before
#405) uses this iteration's regret-matching strategy. `ranges="average"` uses a snapshot of the average
strategy, refreshed every `range_every` iterations: the exact HU-river prototype (#403) found that
features from current-strategy ranges diverge while average-strategy ranges settle. Only the range update
reads the snapshot; sampling and regrets still use the current strategy.

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


RANGES = ("current", "average")
# Iterations between average-strategy snapshots (#405). 2000 is one sync of the CI w4 jobs (4 x E3_SYNC_BATCH),
# so the parallel trainer, which refreshes only at syncs, refreshes every batch there; a refresh normalizes
# every average row once, small next to 2000 hands of tree walks.
RANGE_EVERY = 2000


class E3MCCFR:
    def __init__(self, seed: int = 0, k: int = 5, n: int = 6, depth: str = "full", menu: str = "v1",
                 raise_cap: int | None = G.RAISE_CAP, ranges: str = "current", range_every: int = RANGE_EVERY):
        if ranges not in RANGES:
            raise ValueError(f"ranges must be one of {RANGES}, got {ranges!r}")
        if range_every < 1:
            raise ValueError(f"range_every must be >= 1, got {range_every}")
        self.rng = np.random.default_rng(seed)
        self.k, self.n, self.depth = k, n, depth
        self.menu, self.raise_cap = menu, raise_cap   # game rules (#339); v1 + cap 3 is every earlier run
        self.regret: dict[str, np.ndarray] = {}
        self.avg: dict[str, np.ndarray] = defaultdict(lambda: None)
        self.iterations = 0
        self.nodes = 0
        self.visits: dict[str, int] = defaultdict(int)  # traverser updates per key (coverage diagnostics)
        self.ranges, self.range_every = ranges, range_every
        # average mode: normalized average rows as of iteration `snap_at`; keys not in it use the current strategy
        self.snap: dict[str, np.ndarray] = {}
        self.snap_at = 0
        self.snap_frozen = False  # parallel workers read the parent's snapshot and never refresh it

    def refresh_snapshot(self) -> bool:
        """Average mode: retake the snapshot if `range_every` iterations passed since the last one."""
        if self.ranges != "average" or self.snap_frozen or self.iterations - self.snap_at < self.range_every:
            return False
        self.snap = {k: v / v.sum() for k, v in self.avg.items() if v is not None and v.sum() > 0}
        self.snap_at = self.iterations
        return True

    def _range_row(self, key: str, m: int) -> np.ndarray:
        row = self.snap.get(key)
        return self._sigma(key, m) if row is None else row

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
                out[steps == v] = self._range_row(K.key(public, int(v)), m)
            return out
        table = np.array([self._range_row(K.key(public, v), m) for v in range(self.k)])
        out = table[np.maximum(steps, 0)]
        out[steps < 0] = 0.0
        return out

    def iterate(self, iters: int = 1) -> None:
        for _ in range(iters):
            self.refresh_snapshot()
            self.iterations += 1
            s = G.deal(self.rng, self.n, self.menu, self.raise_cap)
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
            return G.apply(s, acts[i]), K.update_range(ranges, p, probs[:, i])

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

    def state(self) -> dict:
        """Everything `iterate` reads, as JSON data; `from_state` continues bit for bit (#301), so a run
        longer than one CI job (300 min) is chained from checkpoints."""
        st = {"version": 1, "k": self.k, "n": self.n, "depth": self.depth, "iterations": self.iterations,
                "nodes": self.nodes, "menu": self.menu, "raise_cap": self.raise_cap, "rng": self.rng.bit_generator.state,
                "regret": {k: v.tolist() for k, v in self.regret.items()},
                "avg": {k: v.tolist() for k, v in self.avg.items() if v is not None}, "visits": dict(self.visits),
                **self._grid()}
        if self.ranges == "average":
            # version 2: code that predates #405 would resume this as a current-range run, so it must refuse it
            st.update(version=2, ranges=self.ranges, range_every=self.range_every, snap_at=self.snap_at,
                      snap={k: v.tolist() for k, v in self.snap.items()})
        return st

    def _grid(self) -> dict:
        # The pro table's board.nut grid is part of its key meaning (#332): 17 -> 5 steps changed `n<nut>`.
        return {"nut_k": K.NUT_K} if self.depth == "pro" else {}

    @classmethod
    def from_state(cls, st: dict) -> "E3MCCFR":
        if st.get("version") not in (1, 2):
            raise ValueError(f"checkpoint version {st.get('version')!r}; this code reads versions 1 and 2")
        if st["depth"] == "pro" and st.get("nut_k", K.K_PRO) != K.NUT_K:
            raise ValueError(f"checkpoint board.nut has {st.get('nut_k', K.K_PRO)} steps; this code uses {K.NUT_K} "
                             "(#332) - start a fresh run instead of resuming it")
        m = cls(0, st["k"], st["n"], st["depth"], st.get("menu", "v1"), st.get("raise_cap", G.RAISE_CAP),
                st.get("ranges", "current"), st.get("range_every", RANGE_EVERY))
        m.rng.bit_generator.state = st["rng"]
        m.iterations, m.nodes = st["iterations"], st["nodes"]
        m.regret = {k: np.array(v, dtype=float) for k, v in st["regret"].items()}
        m.avg.update({k: np.array(v, dtype=float) for k, v in st["avg"].items()})
        m.visits.update(st["visits"])
        m.snap_at = st.get("snap_at", 0)
        m.snap = {k: np.array(v, dtype=float) for k, v in st.get("snap", {}).items()}
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
    ap.add_argument("--ranges", choices=RANGES, default="current", help="strategy that moves the TP-feature ranges (#405)")
    ap.add_argument("--range-every", type=int, default=RANGE_EVERY, help="iterations between average snapshots")
    a = ap.parse_args(argv)
    m = E3MCCFR(a.seed, K.TIER_K[a.tier], a.players, K.TIER_DEPTH[a.tier], a.menu,
                None if a.no_raise_cap else G.RAISE_CAP, a.ranges, a.range_every)
    t0 = time.monotonic()
    m.iterate(a.iters)
    dt = time.monotonic() - t0
    print(json.dumps({"tier": a.tier, "players": a.players, "iters": a.iters, "seconds": round(dt, 1),
                      "iters_per_s": round(a.iters / dt, 3), "nodes_per_iter": round(m.nodes / a.iters, 1),
                      "keys": len(m.regret), "menu": m.menu, "raise_cap": m.raise_cap, "ranges": m.ranges,
                      # the bound counts the v1 legal-action sets only
                      "theoretical_keys": K.theoretical_keys(a.players, m.k, m.depth) if m.menu == "v1" else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
