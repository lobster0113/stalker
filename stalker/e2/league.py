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
champion (mean + 1 SE >= 0), so progress cannot be a cycle of counter-strategies. Member 4 (#226)
is the persona field (`stalker/e2/personas.py`): every snapshot plays each persona head-to-head, the
field mean is the Gate Q1 report, and a candidate that loses to any persona (mean + 1 SE < 0) is not
promoted. The exploiter lives in
`referee/` because its result is also a measurement; here it is the main policy's opponent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from referee.e2.exploiter import exploit, head_to_head
from stalker.e2.abstraction import TIERS
from stalker.e2.mccfr import MCCFR
from stalker.e2.personas import field as persona_field


@dataclass
class Generation:
    gen: int
    iters: int               # main's total self-play iterations at this snapshot
    gain_bb: float           # exploiter's winnings per hand against this snapshot (lower bound)
    stderr_bb: float
    promoted: bool
    vs_pool_bb: float | None = None   # worst head-to-head result against earlier champions (None: no pool yet)
    field_bb: float | None = None     # mean winnings against the persona field (Gate Q1 report; None: no field)
    field_stderr_bb: float | None = None
    worst_persona: str | None = None  # the persona this snapshot does worst against
    vs_worst_persona_bb: float | None = None   # that result, mean + 1 SE
    field_ci95_low_bb: float | None = None     # field mean - 1.96 SE: the Gate Q1 lower bound (#226)
    exploiter_iters: int | None = None         # iterations the exploiter trained this generation (#247)


@dataclass
class League:
    tier: str = "beginner"
    seed: int = 0
    history: list[Generation] = field(default_factory=list)
    champion: dict | None = None
    pool: list[dict] = field(default_factory=list)   # earlier champions, oldest first
    personas: tuple[str, ...] | None = None          # persona field (None: all presets, (): none)
    # The exploiter (#247): its card abstraction (None: the main policy's tier, which it learns fastest
    # against; BASELINE lost at 2e4 iterations in the first CI league), and a floor on its iterations as
    # a share of the policy's total iterations so a fresh exploiter is not outmatched by sheer training.
    exploiter_tier: str | None = None
    exploiter_ratio: float = 0.5
    exploiter_strategy: str = "current"

    def run(self, generations: int, iters_per_gen: int, exploiter_iters: int, hands: int) -> list[Generation]:
        ab = TIERS[self.tier]
        main = MCCFR(self.seed, ab)
        best = None
        for g in range(1, generations + 1):
            main.iterate(iters_per_gen)
            snap = main.policy()
            ex_iters = max(exploiter_iters, int(self.exploiter_ratio * main.iterations))
            r = exploit(snap, ab, iters=ex_iters, hands=hands, seed=self.seed * 1000 + g,
                        ex_abs=TIERS[self.exploiter_tier or self.tier], strategy=self.exploiter_strategy)
            worst = None
            for old in self.pool:
                m, se = head_to_head(snap, ab, old, ab, hands, seed=self.seed * 1000 + 500 + g)
                worst = m + se if worst is None else min(worst, m + se)
            beats_pool = worst is None or worst >= 0
            fld = self._field(snap, ab, hands, self.seed * 1000 + 700 + g)
            beats_field = fld is None or fld[3] >= 0
            promoted = (best is None or r.gain_bb + r.stderr_bb < best.gain_bb) and beats_pool and beats_field
            gen = Generation(g, main.iterations, r.gain_bb, r.stderr_bb, promoted,
                             None if worst is None else round(worst, 4), *(fld or (None,) * 5), ex_iters)
            self.history.append(gen)
            if promoted:
                best, self.champion = gen, snap
                self.pool.append(snap)
        return self.history

    def _field(self, snap: dict, ab, hands: int, seed: int):
        """(field mean, its SE, worst persona, that persona's mean + SE, field mean - 1.96 SE), or None.

        Each persona plays its own deals (seed + 31 i), so the persona results are independent and the
        field SE is sqrt(sum se_i^2) / n (#252 review: shared deals would correlate them and shrink the SE).
        """
        members = persona_field(self.personas) if self.personas != () else []
        if not members:
            return None
        res = {p.name: head_to_head(snap, ab, p, ab, hands, seed + 31 * i) for i, p in enumerate(members)}
        means = np.array([m for m, _ in res.values()])
        ses = np.array([se for _, se in res.values()])
        name = min(res, key=lambda n: res[n][0] + res[n][1])
        mean, se = float(means.mean()), float(np.sqrt((ses ** 2).sum()) / len(ses))
        return (round(mean, 4), round(se, 4), name, round(res[name][0] + res[name][1], 4), round(mean - 1.96 * se, 4))
