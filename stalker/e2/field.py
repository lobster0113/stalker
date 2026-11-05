"""Field play for E2 MCCFR (#306): a tier policy learns against a mixed field, not a copy of itself.

`MCCFR` is same-policy self-play. Users do not face a copy of the TP policy, so here the trainee
(`FieldMCCFR`, any tier) plays each hand against one member drawn from a field of other learners
(default: a beginner, a mid and a baseline policy, each its own MCCFR with its own abstraction).
Per hand and drawn member m: the trainee traverses both seats while m samples from its current
strategy, then m traverses both seats while the trainee samples (population self-play), so every
policy updates regret only at its own turns and its average only where it is sampled. The E1
version, `stalker/e1/tier_league.py`, found this lowers a beginner's exploitability (#290).
With an empty field the loop is exactly `MCCFR.iterate`'s (regression test).
"""
from __future__ import annotations

import math

import numpy as np

from stalker.e2 import game as G
from stalker.e2.abstraction import BASELINE, TIERS, Abstraction
from stalker.e2.mccfr import _SHORT, MCCFR, _sample

FIELD_TIERS = ("beginner", "mid", "baseline")


class FieldMCCFR(MCCFR):
    def __init__(self, seed: int = 0, abstraction: Abstraction = BASELINE, field_tiers: tuple[str, ...] = FIELD_TIERS):
        super().__init__(seed, abstraction)
        # Distinct seeds so the members' own sampling does not mirror the trainee's.
        self.field = [MCCFR(seed * 1000 + 1 + i, TIERS[t]) for i, t in enumerate(field_tiers)]
        self.field_tiers = tuple(field_tiers)

    def _fwalk(self, s: G.State, learner: MCCFR, other: MCCFR, seat: int, hk: str = "") -> float:
        """One external-sampling pass: `learner` (sitting in `seat`) explores all actions and updates regret,
        `other` samples from its current strategy and adds to its average. Returns learner's value in bb."""
        if s.done:
            v = G.payoff(s, self._sd) / G.BB
            return v if seat == 0 else -v
        acts = self._legal.get(hk)
        if acts is None:
            acts = self._legal[hk] = G.legal(s)
        p, st = s.to_act, s.street
        who = learner if p == seat else other
        bk = self._fbk[id(who)]
        b = bk[p][st]
        if b is None:
            b = bk[p][st] = who.abstraction.bucket(s.hole[p], s.board)
        key = f"{p}|{st}|{b}|{hk}"
        sigma = who._sigma(key, len(acts))
        n = len(s.history)

        def child(a):
            ns = G.step(s, a)
            add = _SHORT[a] if len(ns.history) == n + 1 else "".join(_SHORT[h] for h in ns.history[n:])
            return self._fwalk(ns, learner, other, seat, hk + add)

        if p == seat:
            vals = np.array([child(a) for a in acts])
            v = math.fsum((sigma * vals).tolist())   # not BLAS `@` (#481)
            r = who.regret.setdefault(key, np.zeros(len(acts)))
            np.maximum(r + (vals - v), 0, out=r)
            return v
        a = acts[_sample(self.rng, sigma)]
        avg = who.avg[key]
        if avg is None:
            who.avg[key] = who.iterations * sigma
        else:
            avg += who.iterations * sigma
        return child(a)

    def iterate(self, n: int = 1, log=None, every: int = 1) -> None:
        if not self.field:
            return super().iterate(n, log, every)
        import time
        t0 = time.monotonic()
        for i in range(n):
            if log is not None and i and i % every == 0:
                self._log_row(log, t0)
            self.iterations += 1
            for m in self.field:
                m.iterations = self.iterations
            s = G.deal(self.rng)
            self._sd = G.showdown(s)
            opp = self.field[int(self.rng.integers(len(self.field)))]
            self._fbk = {id(m): [[None] * 4, [None] * 4] for m in (self, opp)}
            for learner, other in ((self, opp), (opp, self)):
                for seat in (0, 1):
                    self._fwalk(s, learner, other, seat)
        if log is not None:
            self._log_row(log, t0)

    def save(self, path) -> None:
        raise NotImplementedError("FieldMCCFR checkpoints are not supported; train from scratch (#306)")
