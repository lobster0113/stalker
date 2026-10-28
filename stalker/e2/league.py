"""League v0 for E2 (#202): generations of self-play, each gated by a learned exploiter.

The user's requirement (2026-10-27): the TP-GTO must come out of competition between policies —
self-play plus exploiters, so bluffs, counters and diverse strategies get tried — never a
hand-written rule. Design note #192 §4. v0 has two members:
  main       MCCFR self-play at the tier's TP resolution (the candidate TP-GTO)
  exploiter  a fresh MCCFR best response to each main snapshot (referee/e2/exploiter.py)
A snapshot is promoted only if the exploiter wins less against it than against the last promoted
snapshot (beyond one standard error); otherwise the league keeps the previous champion. The
history (gain per generation, promoted or not) is the learning curve the service can show.
v1 adds member 3, the snapshot pool: a candidate must also not lose head-to-head to any earlier
champion (mean + 1 SE >= 0), so progress cannot be a cycle of counter-strategies. Persona fields
(member 4) come next. The exploiter lives in
`referee/` because its result is also a measurement; here it is the main policy's opponent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from referee.e2.exploiter import exploit, head_to_head
from stalker.e2.abstraction import TIERS
from stalker.e2.mccfr import MCCFR


@dataclass
class Generation:
    gen: int
    iters: int               # main's total self-play iterations at this snapshot
    gain_bb: float           # exploiter's winnings per hand against this snapshot (lower bound)
    stderr_bb: float
    promoted: bool
    vs_pool_bb: float | None = None   # worst head-to-head result against earlier champions (None: no pool yet)


@dataclass
class League:
    tier: str = "beginner"
    seed: int = 0
    history: list[Generation] = field(default_factory=list)
    champion: dict | None = None
    pool: list[dict] = field(default_factory=list)   # earlier champions, oldest first

    def run(self, generations: int, iters_per_gen: int, exploiter_iters: int, hands: int) -> list[Generation]:
        ab = TIERS[self.tier]
        main = MCCFR(self.seed, ab)
        best = None
        for g in range(1, generations + 1):
            main.iterate(iters_per_gen)
            snap = main.policy()
            r = exploit(snap, ab, iters=exploiter_iters, hands=hands, seed=self.seed * 1000 + g)
            worst = None
            for old in self.pool:
                m, se = head_to_head(snap, ab, old, ab, hands, seed=self.seed * 1000 + 500 + g)
                worst = m + se if worst is None else min(worst, m + se)
            beats_pool = worst is None or worst >= 0
            promoted = (best is None or r.gain_bb + r.stderr_bb < best.gain_bb) and beats_pool
            gen = Generation(g, main.iterations, r.gain_bb, r.stderr_bb, promoted,
                             None if worst is None else round(worst, 4))
            self.history.append(gen)
            if promoted:
                best, self.champion = gen, snap
                self.pool.append(snap)
        return self.history
