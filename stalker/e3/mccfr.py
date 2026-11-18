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

A player-mix run also counts, per player count, the hands dealt and the traverser updates (#535), so a result
can say how much of the training each table size got; `mix_counts` reads them with the c1 keys per size.
They draw no random numbers and n-handed runs keep no counts, so neither table moves. A mixed checkpoint with
the counts is version 7; resuming a version 6 one counts from there on and says so in `counted_from`.

A combined key (tp_key "c1", #400) also writes its `key_version`; `from_state` refuses a checkpoint of another
version of the same variant, since its keys mean other things.

What a finished hand is worth is an option (#883, ADR 0026 (b)). `payoff="chip"` (the default, every run before
#883) is the traverser's chip change in BB. `payoff="icm"` is its prize-equity change,
`stalker.e3.icm_payoff.tournament_payoff(hand, the hand's starting stacks, payouts, lam)`, in units of the whole
prize pool (`payouts` normalized to sum 1): the hand's table is taken as the whole remaining tournament. A
checkpoint of it is version 9. With the default nothing changes, so seeded chip runs do not move.

Which tournament environment a hand is dealt in is an option (#886, #385). `ante=0, stage="c"` (the default,
every run before #886) deals cash hands with no ante. `ante=<chips>` deals every hand with `game.deal(ante=...)`
(the big blind posts it for the table, #878) and `stage` is the c1 key's tournament stage (`tp_key.STAGES`); the
walk runs inside `tp_key.using_env(stage, ante > 0)`, so the keys carry `t<stage>1` (or `t<stage>0` without an
ante). Only the c1 key has these slots. A checkpoint of it is version 10. The default takes the old code path.

Which stacks a tournament hand is dealt with is an option (#898, ADR 0027 decisions 4-5). `stacks="bubble:<profile>"`
(profile `even`, `random` or `skewed`) deals every hand with `sample_tournament_stacks(rng, stack_preset,
stack_remaining, stack_level, profile)`: the survivors' chips of a mid-tournament state of that preset, in E3 BB
units at that level's blind. `n` must equal `stack_remaining` and `player_mix` must be empty. A checkpoint of it is
version 11 and holds the sampling setup; `from_state` refuses to resume it with another. `"uniform"` and
`"sampled"` take the old code path, so their runs and checkpoints do not move.

    python -m stalker.e3.mccfr --tier beginner --iters 50 --seed 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np

from stalker.core.icm import MAX_EXACT_PLAYERS
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.icm_payoff import tournament_payoff
from stalker.e3.tournament_stacks import sample_tournament_stacks
from stalker.tournament.start_state import STACK_PROFILES

AVG_RULES = ("legacy", "own")
BUBBLE_PREFIX = "bubble:"

RANGES = ("current", "average")
STACKS = ("uniform", "sampled")
PAYOFFS = ("chip", "icm")
# Iterations between average-strategy snapshots (#405). 2000 is one sync of the CI w4 jobs (4 x E3_SYNC_BATCH),
# so the parallel trainer, which refreshes only at syncs, refreshes every batch there; a refresh normalizes
# every average row once, small next to 2000 hands of tree walks.
RANGE_EVERY = 2000


class E3MCCFR:
    def __init__(self, seed: int = 0, k: int = 5, n: int = 6, depth: str = "full", menu: str = "v1",
                 raise_cap: int | None = G.RAISE_CAP, ranges: str = "current", range_every: int = RANGE_EVERY,
                 avg_rule: str = "legacy", key_variant: str = "", stacks: str = "uniform",
                 player_mix: tuple[int, ...] = (), avg_cap: float | None = None, payoff: str = "chip",
                 payouts=None, lam: float = 0.0, ante: int = 0, stage: str = "c",
                 stack_preset: str = "", stack_remaining: int = 0, stack_level: int = 0):
        if avg_cap is not None and (avg_rule != "own" or not avg_cap >= 1):
            raise ValueError(f"avg_cap={avg_cap!r}: needs avg_rule 'own' and a cap >= 1 (#448)")
        player_mix = tuple(int(x) for x in player_mix)
        if player_mix and not all(2 <= x <= 9 for x in player_mix):
            raise ValueError(f"player_mix counts must be 2..9, got {player_mix}")
        bubble = stacks.startswith(BUBBLE_PREFIX)
        if not bubble and stacks not in STACKS:
            raise ValueError(f"stacks must be one of {STACKS} or 'bubble:<profile>', got {stacks!r}")
        if bubble:
            if stacks[len(BUBBLE_PREFIX):] not in STACK_PROFILES:
                raise ValueError(f"stacks {stacks!r}: the profile must be one of {STACK_PROFILES}")
            if not stack_preset or stack_remaining < 1:
                raise ValueError(f"stacks {stacks!r} needs stack_preset (a tournament preset) and stack_remaining "
                                 "(survivors, = n)")
            if player_mix or max(player_mix or (n,)) != stack_remaining:
                raise ValueError(f"stacks {stacks!r}: n={n} must equal stack_remaining={stack_remaining} and "
                                 "player_mix must be empty - every hand is the same survivors' table")
        elif stack_preset or stack_remaining or stack_level:
            raise ValueError("stack_preset / stack_remaining / stack_level only go with stacks='bubble:<profile>'")
        self.stack_preset, self.stack_remaining, self.stack_level = stack_preset, stack_remaining, stack_level
        if key_variant not in K.VARIANTS:
            raise ValueError(f"key_variant must be one of {K.VARIANTS}, got {key_variant!r}")
        if ranges not in RANGES:
            raise ValueError(f"ranges must be one of {RANGES}, got {ranges!r}")
        if range_every < 1:
            raise ValueError(f"range_every must be >= 1, got {range_every}")
        if avg_rule not in AVG_RULES:
            raise ValueError(f"avg_rule must be one of {AVG_RULES}, got {avg_rule!r}")
        self.ante, self.stage = check_env(ante, stage, key_variant)
        self.payoff, self.payouts, self.lam = payoff, *check_payoff(payoff, payouts, lam, max(player_mix or (n,)))
        self.hand_stacks: tuple[int, ...] = ()   # starting stacks of the hand being walked (read by payoff "icm")
        self._icm_cache: dict[tuple[int, ...], np.ndarray] = {}
        self.avg_rule = avg_rule
        self.avg_cap = avg_cap   # #529: clips the 'own' weight 1/prod(other reach); None = unclipped (every earlier run)
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
        self.mix_hands = dict.fromkeys(sorted(set(player_mix)), 0)   # #535: hands dealt per player count
        self.mix_visits = dict.fromkeys(self.mix_hands, 0)           # #535: traverser updates per player count
        self.counted_from = 0   # iteration the counts start at (a version 6 checkpoint resumed later has none before)
        self.chain: list[dict] = []   # #712: earlier run segments of this table (from a resumed checkpoint)
        self.seg_start = 0            # iteration this process started from
        self.trav_updates = 0   # traverser updates in this process; not saved, only read per hand by iterate
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
            if self.bubble_stacks():
                stacks = sample_tournament_stacks(self.rng, self.stack_preset, self.stack_remaining, self.stack_level,
                                                  self.stacks[len(BUBBLE_PREFIX):], min_chips=2 * G.BB)
            else:
                stacks = G.sample_stacks(self.rng, n) if self.stacks == "sampled" else None
            if self.tournament_env():
                s = G.deal(self.rng, n, self.menu, self.raise_cap, stacks, ante=self.ante)
            else:   # the old call, so default runs take exactly the code path they always did
                s = G.deal(self.rng, n, self.menu, self.raise_cap, stacks)
            if self.payoff == "icm":   # `total` holds the big blind's ante too, so this is the stack before it
                self.hand_stacks = tuple(s.stack[i] + s.total[i] for i in range(n))
                self._icm_cache = {}
            t0 = self.trav_updates
            if self.tournament_env():
                with K.using_env(self.stage, self.ante > 0):
                    for trav in range(n):
                        self._walk(s, K.initial_ranges(n), trav, [1.0] * n)
            else:
                for trav in range(n):
                    self._walk(s, K.initial_ranges(n), trav, [1.0] * n)
            if self.player_mix:
                self.mix_hands[n] += 1
                self.mix_visits[n] += self.trav_updates - t0

    def bubble_stacks(self) -> bool:
        """Hands are dealt the survivors' tournament stacks (#898)."""
        return self.stacks.startswith(BUBBLE_PREFIX)

    def tournament_env(self) -> bool:
        """A non-default ante or stage (#886): deals, keys and checkpoint (version 10) carry them."""
        return self.ante > 0 or self.stage != "c"

    def _walk(self, s: G.State, ranges: list[np.ndarray], trav: int, reach: list[float]) -> float:
        # reach[m]: the sigma product of seat m's sampled actions above this node (read by avg_rule "own")
        if s.done:
            if self.payoff == "icm":
                return float(self._icm(s)[trav])
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
            self.trav_updates += 1
            return v
        i = int(self.rng.choice(len(acts), p=sigma))
        avg = self.avg[key]
        if self.avg_rule == "legacy":
            self.avg[key] = (avg if avg is not None else 0) + self.iterations * sigma
            return self._walk(*child(i), trav, reach)
        others = math.prod(r for m, r in enumerate(reach) if m != p and m != trav)
        # no cap keeps the original `t / prod` so earlier runs stay bit for bit (t * (1 / prod) differs by an ulp)
        w = self.iterations / others if self.avg_cap is None else self.iterations * min(1 / others, self.avg_cap)
        self.avg[key] = (avg if avg is not None else 0) + w * sigma
        nxt = reach.copy()
        nxt[p] *= float(sigma[i])
        return self._walk(*child(i), trav, nxt)

    def _icm(self, s: G.State) -> np.ndarray:
        # Many leaves of one hand end with the same chip change (folds especially); exact ICM is the costly part.
        delta = tuple(int(x) for x in G.payoff(s))
        v = self._icm_cache.get(delta)
        if v is None:
            v = self._icm_cache[delta] = tournament_payoff(s, self.hand_stacks, self.payouts, self.lam)
        return v

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
            # version 7 (#535): with the per-size counts; code that predates it would resume this and drop them
            st.update(version=7, player_mix=list(self.player_mix), stacks=self.stacks, key_variant=self.key_variant,
                      ranges=self.ranges, range_every=self.range_every, snap_at=self.snap_at,
                      snap={k: v.tolist() for k, v in self.snap.items()}, **self._count_state())
        if self.avg_cap is not None:   # version 8 (#529): code that predates it would resume this with unclipped weights
            st.update(version=8, avg_cap=self.avg_cap, player_mix=list(self.player_mix), stacks=self.stacks,
                      key_variant=self.key_variant, ranges=self.ranges, range_every=self.range_every,
                      snap_at=self.snap_at, snap={k: v.tolist() for k, v in self.snap.items()},
                      **(self._count_state() if self.player_mix else {}))
        if self.payoff != "chip":   # version 9 (#883): code that predates it would resume this on chip rewards
            st.update(version=9, payoff=self.payoff, payouts=list(self.payouts), lam=self.lam,
                      player_mix=list(self.player_mix), stacks=self.stacks, key_variant=self.key_variant,
                      ranges=self.ranges, range_every=self.range_every, snap_at=self.snap_at,
                      snap={k: v.tolist() for k, v in self.snap.items()},
                      **({"avg_cap": self.avg_cap} if self.avg_cap is not None else {}),
                      **(self._count_state() if self.player_mix else {}))
        if self.tournament_env() or self.bubble_stacks():
            # version 10 (#886): code that predates it would resume this on cash deals;
            # version 11 (#898) adds the tournament stack sampling, which version 10 code would resume on 100BB tables
            st.update(version=11 if self.bubble_stacks() else 10, ante=self.ante, stage=self.stage,
                      **({"payoff": self.payoff, "payouts": list(self.payouts), "lam": self.lam}
                         if self.payoff != "chip" else {}),
                      player_mix=list(self.player_mix), stacks=self.stacks, key_variant=self.key_variant,
                      ranges=self.ranges, range_every=self.range_every, snap_at=self.snap_at,
                      snap={k: v.tolist() for k, v in self.snap.items()},
                      **({"avg_cap": self.avg_cap} if self.avg_cap is not None else {}),
                      **(self._count_state() if self.player_mix else {}))
            if self.bubble_stacks():
                st.update(stack_preset=self.stack_preset, stack_remaining=self.stack_remaining,
                          stack_level=self.stack_level)
        if self.key_variant in K.KEY_VERSIONS:   # #400: a combined key's checkpoint names the key version it holds
            st["key_version"] = K.KEY_VERSIONS[self.key_variant]
        st["chain"] = self.resume_chain()   # #712: additive, so the version stays (older code ignores it)
        return st

    def rng_sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.rng.bit_generator.state, sort_keys=True).encode()).hexdigest()

    def resume_chain(self) -> list[dict]:
        """#712: the runs this table went through, the current one last. Each entry's `rng_sha256` is the RNG state
        it ended with; `from_state` checks the next run starts from exactly that."""
        if self.chain and self.iterations == self.seg_start:   # nothing trained since the load: no new segment
            return [dict(c) for c in self.chain]
        return [*(dict(c) for c in self.chain),
                {"run_id": os.environ.get("GITHUB_RUN_ID") or None, "from_iters": self.seg_start,
                 "to_iters": self.iterations, "rng_sha256": self.rng_sha256()}]

    def _count_state(self) -> dict:
        """The #535 counters as checkpoint data (version 7; also the pod summary's `model` block)."""
        return {"mix_counts": {str(n): {"hands": self.mix_hands[n], "visits": self.mix_visits[n]} for n in self.mix_hands},
                "counted_from": self.counted_from}

    def mix_counts(self) -> dict[str, dict[str, int | None]]:
        """Per dealt player count: hands, traverser updates and, for the c1 key (whose non-call keys name the
        player count, `n<players>`), the regret-table keys of that size; other keys hold no player count, so
        `keys` is None there. `call|...` keys of every size are shared and counted by `shared_keys`."""
        per = self._keys_by_players()
        return {str(n): {"hands": self.mix_hands[n], "visits": self.mix_visits[n],
                         "keys": None if per is None else per.get(n, 0)} for n in self.mix_hands}

    def shared_keys(self) -> int | None:
        """c1 keys that no player count owns (the short `call|` keys); None for keys without a player count."""
        per = self._keys_by_players()
        return None if per is None else len(self.regret) - sum(per.values())

    def _keys_by_players(self) -> dict[int, int] | None:
        if self.key_variant != "c1":
            return None
        out: dict[int, int] = defaultdict(int)
        for k in self.regret:
            n = key_players(k)
            if n is not None:
                out[n] += 1
        return dict(out)

    def _grid(self) -> dict:
        # The pro table's board.nut grid is part of its key meaning (#332): 17 -> 5 steps changed `n<nut>`.
        return {"nut_k": K.NUT_K} if self.depth == "pro" else {}

    @classmethod
    def from_state(cls, st: dict, avg_rule: str | None = None,
                   player_mix: tuple[int, ...] | None = None, avg_cap: float | None = None,
                   payoff: str | None = None, ante: int | None = None, stage: str | None = None,
                   stack_sample: tuple[str, int, int] | None = None) -> "E3MCCFR":
        """`avg_rule` / `player_mix` / `payoff` / `ante` / `stage`, if given, are what the caller means to continue
        with; a checkpoint of another is refused. Checkpoints before version 9 hold no payoff and are chip runs,
        before version 10 no ante or stage and are cash runs (ante 0, stage "c")."""
        if stack_sample is not None and stack_sample != (st.get("stack_preset", ""), st.get("stack_remaining", 0),
                                                         st.get("stack_level", 0)):
            raise ValueError(f"checkpoint was dealt stacks of {(st.get('stack_preset', ''), st.get('stack_remaining', 0), st.get('stack_level', 0))}, "
                             f"not {stack_sample} (#898); resume it with its own (preset, remaining, level) or start a fresh run")
        if st.get("version") not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11):
            raise ValueError(f"checkpoint version {st.get('version')!r}; this code reads versions 1 to 11")
        v10 = st["version"] in (10, 11)
        env = (st.get("ante", 0), st.get("stage", "c"))
        if env != (0, "c") and not v10 or st["version"] == 10 and env == (0, "c"):
            raise ValueError(f"checkpoint version {st['version']} with ante/stage {env}: a tournament-environment "
                             "checkpoint is version 10 and only that one has an ante or stage (#886)")
        for name, want, have in (("ante", ante, env[0]), ("stage", stage, env[1])):
            if want is not None and want != have:
                raise ValueError(f"checkpoint was trained with {name} {have!r}, not {want!r} (#886); the regrets of "
                                 "two environments must not mix - resume it with its own ante/stage or start a "
                                 "fresh run")
        pay = st.get("payoff", "chip")
        if not v10 and (pay != "chip") != (st["version"] == 9):
            raise ValueError(f"checkpoint version {st['version']} with payoff {pay!r}: a non-chip payoff checkpoint "
                             "is version 9 (or 10) and only those have a payoff (#883)")
        if payoff is not None and payoff != pay:
            raise ValueError(f"checkpoint was trained on payoff {pay!r}, not {payoff!r} (#883); the regrets of two "
                             "rewards must not mix - resume it with its own payoff or start a fresh run")
        cap = st.get("avg_cap")
        if (st["version"] == 8 and cap is None) or (cap is not None and st["version"] not in (8, 9, 10, 11)) \
                or (avg_cap is not None and avg_cap != cap):
            raise ValueError(f"checkpoint version {st['version']} holds avg_cap {cap!r}, asked {avg_cap!r} (#529); "
                             "the weights must not mix in one average - resume it with its own cap or start a fresh run")
        mix = tuple(st.get("player_mix", ()))
        if st["version"] not in (8, 9, 10, 11) and bool(mix) != (st["version"] in (6, 7)):
            raise ValueError(f"checkpoint version {st['version']} with player_mix {list(mix)}: a mixed-player "
                             "checkpoint is version 6 or 7 and only those have a player_mix")
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
                st.get("stacks", "uniform"), mix, cap, pay, st.get("payouts"), st.get("lam", 0.0), *env,
                st.get("stack_preset", ""), st.get("stack_remaining", 0), st.get("stack_level", 0))
        if pay != "chip":   # saved payouts are already normalized; normalizing again can move the last bit (#883)
            m.payouts = tuple(float(x) for x in st["payouts"])
        m.rng.bit_generator.state = st["rng"]
        m.iterations, m.nodes = st["iterations"], st["nodes"]
        m.chain, m.seg_start = [dict(c) for c in st.get("chain", [])], m.iterations   # old checkpoints: no chain
        if m.chain and m.chain[-1].get("rng_sha256") not in (None, m.rng_sha256()):
            raise ValueError("checkpoint RNG state does not match the hash its last run saved (#712): the file was "
                             "edited or mixed with another run's - resume the checkpoint as that run wrote it, "
                             "or start a fresh run")
        m.regret = {k: np.array(v, dtype=float) for k, v in st["regret"].items()}
        m.avg.update({k: np.array(v, dtype=float) for k, v in st["avg"].items()})
        m.visits.update(st["visits"])
        m.snap_at = st.get("snap_at", 0)
        m.snap = {k: np.array(v, dtype=float) for k, v in st.get("snap", {}).items()}
        if "mix_counts" in st:
            for n, c in st["mix_counts"].items():
                m.mix_hands[int(n)], m.mix_visits[int(n)] = c["hands"], c["visits"]
            m.counted_from = st["counted_from"]
        elif mix and st["version"] == 6:   # version 6 (before #535): nothing was counted up to here
            m.counted_from = m.iterations
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


def key_players(key: str) -> int | None:
    """The player count a c1 key names (`<pos>|n<players>|`, `b|n<players>|`, `p|<pos>|n<players>|`); None for
    a `call|` key, which has no such field. Only c1 keys carry it: other keys must not be read with this."""
    if key.startswith("call|"):
        return None
    for f in key.split("|", 3)[1:3]:
        if f[:1] == "n" and f[1:].isdigit():
            return int(f[1:])
    return None


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


def visit_quantiles(m: E3MCCFR, keys=None) -> dict:
    """#711: how filled the table is, from the per-key traverser update counts (p10..p90, `lower` so values stay
    integers). `keys` limits it to a subset (e.g. one player count); no visits gives only {"keys": 0}."""
    import numpy as np
    v = [x for k, x in m.visits.items() if keys is None or k in keys]
    if not v:
        return {"keys": 0}
    a = np.asarray(v)
    out = {f"p{q}": int(np.quantile(a, q / 100, method="lower")) for q in (10, 25, 50, 75, 90)}
    return {"keys": len(v), "under10": int((a < 10).sum()), **out}


def check_payoff(payoff: str, payouts, lam, max_players: int) -> tuple[tuple[float, ...], float]:
    """Validated (payouts normalized to sum 1, lam) for `E3MCCFR`; chip runs get ((), 0.0). `payouts` is a
    stalker/tournament/presets name or a list of prizes by finishing place."""
    if payoff not in PAYOFFS:
        raise ValueError(f"payoff must be one of {PAYOFFS}, got {payoff!r}")
    if payoff == "chip":
        if payouts is not None or lam:
            raise ValueError(f"payouts={payouts!r} / lam={lam!r} are only read by payoff 'icm' (#883); "
                             "drop them or pass payoff='icm'")
        return (), 0.0
    if payouts is None:
        raise ValueError("payoff 'icm' needs payouts: a preset name (e.g. '6max_sng_wta') or prizes by place, "
                         "e.g. [0.65, 0.35]")
    if isinstance(payouts, str):
        from stalker.tournament.config import ConfigError, load_preset
        try:
            payouts = load_preset(payouts).payout_ratios()
        except ConfigError as e:
            raise ValueError(f"payouts {payouts!r}: {e}") from None
    try:
        p = [float(x) for x in payouts]
    except (TypeError, ValueError):
        raise ValueError(f"payouts {payouts!r}: need a preset name or a list of numbers by place") from None
    if not p or not all(math.isfinite(x) and x >= 0 for x in p) or sum(p) <= 0 \
            or any(a < b for a, b in zip(p, p[1:])):
        raise ValueError(f"payouts {payouts!r}: need non-negative, non-increasing prizes by place with a "
                         "positive total, e.g. [0.5, 0.3, 0.2]")
    try:
        lam = float(lam)
    except (TypeError, ValueError):
        raise ValueError(f"lam {lam!r}: need a number in [0, 1] (ADR 0026)") from None
    if not 0.0 <= lam <= 1.0:
        raise ValueError(f"lam {lam!r}: need a number in [0, 1] (ADR 0026), 0 = pure ICM")
    if max_players > MAX_EXACT_PLAYERS:
        raise ValueError(f"{max_players} players exceed the exact ICM limit {MAX_EXACT_PLAYERS}: payoff 'icm' is "
                         "for one final table; use payoff 'chip' or fewer players")
    total = math.fsum(p)
    return tuple(x / total for x in p), lam


def check_env(ante, stage: str, key_variant: str) -> tuple[int, str]:
    """Validated (ante, stage) for `E3MCCFR` (#886). Only the c1 key has the environment slots (`t<stage><ante>`)."""
    if isinstance(ante, bool) or not isinstance(ante, (int, np.integer)):
        raise ValueError(f"ante {ante!r}: chips as an int, e.g. ante={G.BB} for a BB ante (0 = no ante)")
    if ante < 0:
        raise ValueError(f"ante {ante}: must not be negative; use 0 for no ante or e.g. {G.BB} for a BB ante")
    if stage not in K.STAGES:
        raise ValueError(f"stage {stage!r}: must be one of {K.STAGES} (tp_key.STAGES; 'c' = cash)")
    if (ante > 0 or stage != "c") and key_variant != "c1":
        raise ValueError(f"ante {ante} / stage {stage!r} need key_variant 'c1' (got {key_variant!r}): only the c1 "
                         "key has the t<stage><ante> slots; pass key_variant='c1' or keep ante=0, stage='c'")
    return int(ante), stage


def parse_mix(text: str) -> tuple[int, ...]:
    """"2,3,4,5,6" -> (2, 3, 4, 5, 6); "" -> () (every hand n-handed)."""
    try:
        mix = tuple(int(x) for x in text.split(",") if x.strip())
    except ValueError:
        raise argparse.ArgumentTypeError(f"player mix {text!r}: comma-separated player counts, e.g. 2,3,4,5,6")
    if not all(2 <= x <= 9 for x in mix):
        raise argparse.ArgumentTypeError(f"player mix {text!r}: counts must be 2..9")
    return mix


def parse_payouts(text: str):
    """"0.65,0.35" -> [0.65, 0.35]; anything else is a preset name (checked by `check_payoff`)."""
    try:
        return [float(x) for x in text.split(",") if x.strip()]
    except ValueError:
        return text


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
    ap.add_argument("--payoff", choices=PAYOFFS, default="chip", help="icm: prize-equity change reward (#883)")
    ap.add_argument("--payouts", type=parse_payouts, default=None,
                    help="payoff icm: preset name (stalker/tournament/presets) or prizes by place, e.g. 0.65,0.35")
    ap.add_argument("--lam", type=float, default=0.0, help="payoff icm: bubble correction (ADR 0026), 0 = pure ICM")
    ap.add_argument("--ante", type=int, default=0, help=f"BB ante in chips (#886, c1 key), e.g. {G.BB}; 0 = none")
    ap.add_argument("--stage", choices=K.STAGES, default="c", help="c1 key tournament stage (#886); c = cash")
    a = ap.parse_args(argv)
    m = E3MCCFR(a.seed, K.TIER_K[a.tier], a.players, K.TIER_DEPTH[a.tier], a.menu,
                None if a.no_raise_cap else G.RAISE_CAP, a.ranges, a.range_every, a.avg_rule, a.key_variant,
                a.stacks, a.player_mix, payoff=a.payoff, payouts=a.payouts, lam=a.lam, ante=a.ante, stage=a.stage)
    t0 = time.monotonic()
    m.iterate(a.iters)
    dt = time.monotonic() - t0
    print(json.dumps({"tier": a.tier, "players": a.players, "iters": a.iters, "seconds": round(dt, 1),
                      "iters_per_s": round(a.iters / dt, 3), "nodes_per_iter": round(m.nodes / a.iters, 1),
                      "keys": len(m.regret), "menu": m.menu, "raise_cap": m.raise_cap, "ranges": m.ranges,
                      "key_variant": m.key_variant, "stacks": m.stacks, "player_mix": list(m.player_mix),
                      "payoff": m.payoff, "payouts": list(m.payouts), "lam": m.lam, "ante": m.ante, "stage": m.stage,
                      # the bound counts the v1 legal-action sets only
                      "theoretical_keys": K.theoretical_keys(a.players, m.k, m.depth, m.key_variant) if m.menu == "v1" else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
