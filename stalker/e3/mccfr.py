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

How the average strategy is accumulated is an option (#426). Both rules add sigma at a seat's node during
the other seats' traversals. `avg_rule="legacy"` (the default, every run before #426) adds it as is: the
visit is reached with the chance, own and every other non-traverser's reach, so from three players on the
other opponents' reach weights the average too (#414 oracle). `avg_rule="own"` divides the increment by
the sigma product of the other non-traversers' sampled actions above the node, so in expectation it is
weighted by chance and own reach only. Heads-up there is nobody to divide out and the two are bit-identical.

Which stacks a hand is dealt with is an option (#399). `stacks="uniform"` (the default, every run before #399)
gives every seat 100BB. `stacks="sampled"` draws each hand's table with `game.sample_stacks` (20-250BB, half
the tables equal) from the same generator, so the stack key variants (tp_key "s2", "s2me") see short, deep
and mixed tables; a checkpoint of it is version 5.

How many players a hand is dealt is an option (#486, ADR 0019 D). `player_mix=()` (the default, every run
before #486) deals every hand to `n` players. `player_mix=(2, 3, 4, 5, 6)` draws each hand's player count
uniformly from the tuple, from the same generator and before the stacks (repeat a count to weight it), so the
c1 key's `n<players>` and position fields see every table size; `n` is then the evaluation table (LBR, field).
With the default nothing extra is drawn, so seeded runs do not move. A checkpoint of it is version 6.

A combined key (tp_key "c1", #400) also writes its `key_version`; `from_state` refuses a checkpoint of another
version of the same variant, since its keys mean other things.

    python -m stalker.e3.mccfr --tier beginner --iters 50 --seed 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import defaultdict

import numpy as np

from stalker.e3 import game as G
from stalker.e3 import tp_key as K

AVG_RULES = ("legacy", "own")

RANGES = ("current", "average")
STACKS = ("uniform", "sampled")
# Iterations between average-strategy snapshots (#405). 2000 is one sync of the CI w4 jobs (4 x E3_SYNC_BATCH),
# so the parallel trainer, which refreshes only at syncs, refreshes every batch there; a refresh normalizes
# every average row once, small next to 2000 hands of tree walks.
RANGE_EVERY = 2000


class E3MCCFR:
    def __init__(self, seed: int = 0, k: int = 5, n: int = 6, depth: str = "full", menu: str = "v1",
                 raise_cap: int | None = G.RAISE_CAP, ranges: str = "current", range_every: int = RANGE_EVERY,
                 avg_rule: str = "legacy", key_variant: str = "", stacks: str = "uniform",
                 player_mix: tuple[int, ...] = ()):
        player_mix = tuple(int(x) for x in player_mix)
        if player_mix and not all(2 <= x <= 9 for x in player_mix):
            raise ValueError(f"player_mix counts must be 2..9, got {player_mix}")
        if stacks not in STACKS:
            raise ValueError(f"stacks must be one of {STACKS}, got {stacks!r}")
        if key_variant not in K.VARIANTS:
            raise ValueError(f"key_variant must be one of {K.VARIANTS}, got {key_variant!r}")
        if ranges not in RANGES:
            raise ValueError(f"ranges must be one of {RANGES}, got {ranges!r}")
        if range_every < 1:
            raise ValueError(f"range_every must be >= 1, got {range_every}")
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
        self.ranges, self.range_every = ranges, range_every
        self.key_variant = key_variant   # "b1" (#398): suit-aware outs/vuln/block in the key; "" is every earlier table
        self.stacks = stacks             # "sampled" (#399): per-hand 20-250BB tables; "uniform" 100BB is every earlier run
        self.player_mix = player_mix     # (#486): per-hand player counts; () deals every hand to n
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
            # one row per distinct value, then a single gather (no per-value mask pass)
            vals, inv = np.unique(steps, return_inverse=True)
            first = int(np.searchsorted(vals, 0))   # vals[:first] are the -1 collisions
            table = np.zeros((len(vals), m))
            for j in range(first, len(vals)):
                table[j] = self._range_row(K.key(public, int(vals[j])), m)
            return table[inv.reshape(-1)]
        table = np.array([self._range_row(K.key(public, v), m) for v in range(self.k)])
        out = table[np.maximum(steps, 0)]
        out[steps < 0] = 0.0
        return out

    def iterate(self, iters: int = 1) -> None:
        for _ in range(iters):
            self.refresh_snapshot()
            self.iterations += 1
            n = self.player_mix[int(self.rng.integers(len(self.player_mix)))] if self.player_mix else self.n
            stacks = G.sample_stacks(self.rng, n) if self.stacks == "sampled" else None
            s = G.deal(self.rng, n, self.menu, self.raise_cap, stacks)
            for trav in range(n):
                self._walk(s, K.initial_ranges(n), trav, [1.0] * n)

    def _walk(self, s: G.State, ranges: list[np.ndarray], trav: int, reach: list[float]) -> float:
        # reach[m]: the sigma product of seat m's sampled actions above this node (read by avg_rule "own")
        if s.done:
            return float(G.payoff(s)[trav]) / G.BB
        self.nodes += 1
        acts = G.legal(s)
        p = s.to_act
        steps = K.equity_steps(s, p, ranges, self.k, self.key_variant, self.depth)
        public = K.public_key(s, p, self.depth, self.key_variant)
        key = K.key(public, K.my_step(steps, s, p))
        sigma = self._sigma(key, len(acts))
        probs = self._seat_probs(public, steps, len(acts))

        def child(i: int):
            return G.apply(s, acts[i]), K.update_range(ranges, p, probs[:, i])

        if p == trav:
            vals = np.array([self._walk(*child(i), trav, reach) for i in range(len(acts))])
            v = math.fsum((sigma * vals).tolist())   # not BLAS `@`: CPU-dependent last bits (#447)
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
        st = {"version": 1, "avg_rule": self.avg_rule,
                "k": self.k, "n": self.n, "depth": self.depth, "iterations": self.iterations,
                "nodes": self.nodes, "menu": self.menu, "raise_cap": self.raise_cap, "rng": self.rng.bit_generator.state,
                "regret": {k: v.tolist() for k, v in self.regret.items()},
                "avg": {k: v.tolist() for k, v in self.avg.items() if v is not None}, "visits": dict(self.visits),
                **self._grid()}
        if self.ranges == "average" or self.key_variant:
            # version 2: code that predates #405 would resume this as a current-range run, so it must refuse it
            st.update(version=2, ranges=self.ranges, range_every=self.range_every, snap_at=self.snap_at,
                      snap={k: v.tolist() for k, v in self.snap.items()})
        if self.avg_rule == "own":
            # version 3 (#426): code that predates avg_rule would resume an "own" checkpoint as legacy, so it must refuse it
            st["version"] = 3
        if self.key_variant:   # version 4 (#398): code that predates it would resume this with plain keys
            st.update(version=4, key_variant=self.key_variant)
        if self.stacks != "uniform":   # version 5 (#399): code that predates it would resume this on 100BB tables
            st.update(version=5, stacks=self.stacks, key_variant=self.key_variant, ranges=self.ranges,
                      range_every=self.range_every, snap_at=self.snap_at,
                      snap={k: v.tolist() for k, v in self.snap.items()})
        if self.player_mix:   # version 6 (#486): code that predates it would resume this with n-handed deals only
            st.update(version=6, player_mix=list(self.player_mix), stacks=self.stacks, key_variant=self.key_variant,
                      ranges=self.ranges, range_every=self.range_every, snap_at=self.snap_at,
                      snap={k: v.tolist() for k, v in self.snap.items()})
        if self.key_variant in K.KEY_VERSIONS:   # #400: a combined key's checkpoint names the key version it holds
            st["key_version"] = K.KEY_VERSIONS[self.key_variant]
        return st

    def _grid(self) -> dict:
        # The pro table's board.nut grid is part of its key meaning (#332): 17 -> 5 steps changed `n<nut>`.
        return {"nut_k": K.NUT_K} if self.depth == "pro" else {}

    @classmethod
    def from_state(cls, st: dict, avg_rule: str | None = None,
                   player_mix: tuple[int, ...] | None = None) -> "E3MCCFR":
        """`avg_rule` / `player_mix`, if given, are what the caller means to continue with; a checkpoint of
        another is refused."""
        if st.get("version") not in (1, 2, 3, 4, 5, 6):
            raise ValueError(f"checkpoint version {st.get('version')!r}; this code reads versions 1 to 6")
        mix = tuple(st.get("player_mix", ()))
        if bool(mix) != (st["version"] == 6):
            raise ValueError(f"checkpoint version {st['version']} with player_mix {list(mix)}: a mixed-player "
                             "checkpoint is version 6 and only it has a player_mix")
        if player_mix is not None and tuple(player_mix) != mix:
            raise ValueError(f"checkpoint was dealt with player_mix {list(mix)}, not {list(player_mix)} (#486); "
                             "resume it with its own mix or start a fresh run")
        rule = st.get("avg_rule", "legacy")    # checkpoints before #426 are all legacy
        if st["version"] < 4 and (rule == "own") != (st["version"] == 3):
            raise ValueError(f"checkpoint version {st['version']} with avg_rule {rule!r}: an avg_rule 'own' "
                             "checkpoint is version 3, a legacy one version 1 or 2")
        if avg_rule is not None and avg_rule != rule:
            raise ValueError(f"checkpoint average strategy was accumulated with avg_rule {rule!r}, not {avg_rule!r} "
                             "(#426); the two rules must not mix in one average - resume it with its own rule "
                             "or start a fresh run")
        if st["depth"] == "pro" and st.get("nut_k", K.K_PRO) != K.NUT_K:
            raise ValueError(f"checkpoint board.nut has {st.get('nut_k', K.K_PRO)} steps; this code uses {K.NUT_K} "
                             "(#332) - start a fresh run instead of resuming it")
        kv = st.get("key_variant", "")
        if kv in K.KEY_VERSIONS and st.get("key_version") != K.KEY_VERSIONS[kv]:
            raise ValueError(f"checkpoint key {kv!r} version {st.get('key_version')!r}; this code builds version "
                             f"{K.KEY_VERSIONS[kv]} (#400) - its keys mean other things, start a fresh run")
        m = cls(0, st["k"], st["n"], st["depth"], st.get("menu", "v1"), st.get("raise_cap", G.RAISE_CAP),
                st.get("ranges", "current"), st.get("range_every", RANGE_EVERY), rule, st.get("key_variant", ""),
                st.get("stacks", "uniform"), mix)
        m.rng.bit_generator.state = st["rng"]
        m.iterations, m.nodes = st["iterations"], st["nodes"]
        m.regret = {k: np.array(v, dtype=float) for k, v in st["regret"].items()}
        m.avg.update({k: np.array(v, dtype=float) for k, v in st["avg"].items()})
        m.visits.update(st["visits"])
        m.snap_at = st.get("snap_at", 0)
        m.snap = {k: np.array(v, dtype=float) for k, v in st.get("snap", {}).items()}
        return m

    def regret_hash(self) -> str:
        """sha256 of the regret table: keys in sorted order, each with its row's length and float64 bytes.
        Recorded with every CI result (#447), so two runs that should match can be checked bit for bit."""
        h = hashlib.sha256()
        for k in sorted(self.regret):
            r = np.ascontiguousarray(self.regret[k], dtype="<f8")
            h.update(k.encode("utf-8") + b"\0" + len(r).to_bytes(4, "little") + r.tobytes())
        return h.hexdigest()

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
        fs = k.split("|")
        while fs[-1].startswith(("o", "a")):   # b1 / b2 labels (#398, #460): the equity or nut step ("e", "n") is never last otherwise
            fs.pop()
        f = fs[by]
        d = out.setdefault(f, {"keys": 0, "under10": 0})
        d["keys"] += 1
        d["under10"] += v < 10
    return out


def parse_mix(text: str) -> tuple[int, ...]:
    """"2,3,4,5,6" -> (2, 3, 4, 5, 6); "" -> () (every hand n-handed)."""
    try:
        mix = tuple(int(x) for x in text.split(",") if x.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"player mix {text!r}: comma-separated player counts, e.g. 2,3,4,5,6")
    if not all(2 <= x <= 9 for x in mix):
        raise argparse.ArgumentTypeError(f"player mix {text!r}: counts must be 2..9")
    return mix


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E3 TP-keyed MCCFR (local reference numbers)")
    ap.add_argument("--tier", choices=sorted(K.TIER_K), default="beginner")
    ap.add_argument("--iters", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--players", type=int, default=6)
    ap.add_argument("--menu", choices=G.MENUS, default="v1")
    ap.add_argument("--no-raise-cap", action="store_true")
    ap.add_argument("--ranges", choices=RANGES, default="current", help="strategy that moves the TP-feature ranges (#405)")
    ap.add_argument("--key-variant", choices=K.VARIANTS, default="",
                    help="b1: suit-aware outs/vuln/block key (#398); b2: b1 + board.adv/opp.value/plan.foldeq (#460); b3: b1 + public facts (#461); s2 / s2me: effective-stack depth (#399); c1: combined cash key (#400)")
    ap.add_argument("--stacks", choices=STACKS, default="uniform", help="sampled: 20-250BB tables (#399)")
    ap.add_argument("--range-every", type=int, default=RANGE_EVERY, help="iterations between average snapshots")
    ap.add_argument("--avg-rule", choices=AVG_RULES, default="legacy")
    ap.add_argument("--player-mix", type=parse_mix, default=(), help="per-hand player counts, e.g. 2,3,4,5,6 (#486)")
    a = ap.parse_args(argv)
    m = E3MCCFR(a.seed, K.TIER_K[a.tier], a.players, K.TIER_DEPTH[a.tier], a.menu,
                None if a.no_raise_cap else G.RAISE_CAP, a.ranges, a.range_every, a.avg_rule, a.key_variant,
                a.stacks, a.player_mix)
    t0 = time.monotonic()
    m.iterate(a.iters)
    dt = time.monotonic() - t0
    print(json.dumps({"tier": a.tier, "players": a.players, "iters": a.iters, "seconds": round(dt, 1),
                      "iters_per_s": round(a.iters / dt, 3), "nodes_per_iter": round(m.nodes / a.iters, 1),
                      "keys": len(m.regret), "menu": m.menu, "raise_cap": m.raise_cap, "ranges": m.ranges,
                      "key_variant": m.key_variant, "stacks": m.stacks, "player_mix": list(m.player_mix),
                      # the bound counts the v1 legal-action sets only
                      "theoretical_keys": K.theoretical_keys(a.players, m.k, m.depth, m.key_variant) if m.menu == "v1" else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
