"""CFR+ on a full game tree (`referee.anchors.toy.game.Node`).

Full traversal with alternating updates, regret matching+ and linearly weighted averaging
(Tammelin 2014), so runs are deterministic and need no random generator. The average strategy is
the one that converges; the current strategy is not.
"""
from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from referee.anchors.toy.game import CHANCE, TERMINAL, Node, infosets


class CFRPlus:
    def __init__(self, root: Node):
        self.root = root
        self.info = infosets(root)
        self.regret = {k: np.zeros(len(a)) for k, (_, a) in self.info.items()}
        self.avg = {k: np.zeros(len(a)) for k, (_, a) in self.info.items()}
        self.iterations = 0
        self._sigma: dict[str, np.ndarray] = {}
        self._delta: dict[str, np.ndarray] = {}

    def _current(self, key: str) -> np.ndarray:
        r = self.regret[key]
        s = r.sum()
        return r / s if s > 0 else np.full(len(r), 1.0 / len(r))

    def _walk(self, n: Node, player: int, reach_self: float, reach_other: float, t: int) -> float:
        """Counterfactual value for `player` (weighted by other players' and chance reach)."""
        if n.kind == TERMINAL:
            return n.utility if player == 0 else -n.utility
        if n.kind == CHANCE:
            return sum(p * self._walk(c, player, reach_self, reach_other * p, t)
                       for p, c in zip(n.probs, n.children))
        sigma = self._sigma[n.infoset]
        if n.player == player:
            vals = np.array([self._walk(c, player, reach_self * sigma[i], reach_other, t)
                             for i, c in enumerate(n.children)])
            v = math.fsum((sigma * vals).tolist())   # not BLAS `@`: CPU-dependent last bits (#481)
            self._delta[n.infoset] += reach_other * (vals - v)
            self.avg[n.infoset] += t * reach_self * sigma
            return v
        return sum(sigma[i] * self._walk(c, player, reach_self, reach_other * sigma[i], t)
                   for i, c in enumerate(n.children))

    def iterate(self, n: int = 1) -> None:
        for _ in range(n):
            self.iterations += 1
            for player in (0, 1):
                # One strategy per infoset per pass: regrets apply only after the whole traversal.
                self._sigma = {k: self._current(k) for k in self.info}
                self._delta = {k: np.zeros(len(a)) for k, (_, a) in self.info.items()}
                self._walk(self.root, player, 1.0, 1.0, self.iterations)
                for k, d in self._delta.items():
                    if self.info[k][0] == player:
                        np.maximum(self.regret[k] + d, 0.0, out=self.regret[k])

    def average_strategy(self) -> dict[str, list[float]]:
        out = {}
        for k, s in self.avg.items():
            tot = s.sum()
            out[k] = (s / tot if tot > 0 else np.full(len(s), 1.0 / len(s))).tolist()
        return out


def train(root: Node, iterations: int, every: int, on_log: Callable[[int, dict], None],
          rng: np.random.Generator | None = None) -> dict[str, list[float]]:
    """Run CFR+ and call `on_log(iteration, average_strategy)` every `every` iterations and at the end.

    `rng` is accepted for sampled CFR variants; full-traversal CFR+ does not draw from it.
    """
    if iterations < 1 or every < 1:
        raise ValueError("iterations and every must be >= 1")
    solver = CFRPlus(root)
    while solver.iterations < iterations:
        solver.iterate(min(every, iterations - solver.iterations))
        on_log(solver.iterations, solver.average_strategy())
    return solver.average_strategy()
