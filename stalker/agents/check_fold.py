"""Deterministic check/fold baseline: a trained policy that only matches its ROI has learned nothing more (#78, #88)."""
from __future__ import annotations

from stalker.agents.base import Action, Agent, Observation


class CheckFoldAgent(Agent):
    """Checks when checking is free, folds to any bet. No randomness, no memory."""

    def act(self, observation: Observation) -> Action:
        la = observation.legal
        return Action("fold") if la.call_amount > 0 and la.can_fold else Action("call")
