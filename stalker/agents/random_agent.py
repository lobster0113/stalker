"""Uniform-random legal player; the Gate R invariant tests use it to exercise every tournament path."""
from __future__ import annotations

import numpy as np

from stalker.agents.base import Action, Agent, Observation


class RandomLegalAgent(Agent):
    def __init__(self, rng: np.random.Generator, fold_p: float = 0.2, raise_p: float = 0.25) -> None:
        self.rng = rng
        self.fold_p = fold_p
        self.raise_p = raise_p

    def act(self, observation: Observation) -> Action:
        la = observation.legal
        r = self.rng.random()
        if la.can_fold and la.call_amount > 0 and r < self.fold_p:
            return Action("fold")
        if la.min_raise_to is not None and r > 1 - self.raise_p:
            return Action("raise", int(self.rng.integers(la.min_raise_to, la.max_raise_to + 1)))
        return Action("call")
