"""Parameter-driven rule bots ("personas", plan §3.5, ADR 0010): a target style VPIP/PFR/aggression/fold-to-bet.

Preflop the hand's top-fraction rank (`hand_top_pct`, 0 = best) is compared with `pfr` and `vpip`; postflop a coarse
made-hand strength and `aggression` / `fold_to_bet` drive bet, call and fold. The bot reads only its own `Observation`
(own hole cards + public info) and draws from the injected `numpy.random.Generator`, keeps no state across hands.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from stalker.agents.base import Action, Agent, Observation
from stalker.core.cards import card
from stalker.core.evaluator import category, evaluate
from stalker.core.ranges import hand_top_pct

# The big blind's free check is not voluntary, so it costs ~1/6 of the seats (vpip - pfr) of VPIP; loosen the other
# decisions by this share of (vpip - pfr) to hit the target (calibrated on 6-max, `tests/test_persona.py`).
BB_CHECK_COMP = 0.08
MAX_PREFLOP_RAISES = 4  # beyond this a raise-worthy hand just calls, so 3-bet wars end
_PAIR = 1  # evaluator category: pair (0 = high card, 2 = two pair, 3+ = trips and better)


@dataclass(frozen=True)
class PersonaParams:
    vpip: float  # fraction of hands that voluntarily put chips in preflop
    pfr: float  # fraction of hands raised preflop (<= vpip)
    aggression: float  # postflop (bet+raise)/(bet+raise+call)
    fold_to_bet: float  # tendency to give up a weak hand facing a postflop bet

    def __post_init__(self) -> None:
        for name in ("vpip", "pfr", "aggression", "fold_to_bet"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {getattr(self, name)}")
        if self.pfr > self.vpip:
            raise ValueError("pfr must be <= vpip")


# Values from plan §3.5 where the table gives them. `loose_passive_b` has no table value: a milder variant of
# `loose_passive`, so the nine types still cover the table's "loose passive" rows.
PRESETS: dict[str, PersonaParams] = {
    "calling_station": PersonaParams(0.55, 0.05, 0.12, 0.12),
    "loose_passive": PersonaParams(0.42, 0.09, 0.25, 0.35),
    "maniac": PersonaParams(0.62, 0.42, 0.85, 0.25),
    "weak_tight": PersonaParams(0.17, 0.08, 0.22, 0.78),
    "nit": PersonaParams(0.12, 0.10, 0.40, 0.68),
    "tag": PersonaParams(0.22, 0.18, 0.56, 0.50),
    "lag": PersonaParams(0.30, 0.25, 0.66, 0.40),
    "high_stakes_pro": PersonaParams(0.24, 0.20, 0.60, 0.45),
    "loose_passive_b": PersonaParams(0.36, 0.12, 0.30, 0.30),
}


def persona_params(name: str) -> PersonaParams:
    if name not in PRESETS:
        raise KeyError(f"unknown persona {name!r}; choose from {sorted(PRESETS)}")
    return PRESETS[name]


def _strength(hole: tuple[str, ...], board: tuple[str, ...]) -> float:
    """0..1 made-hand strength. A pair that lives only on the board counts as nothing."""
    cat = category(evaluate([card(c) for c in (*hole, *board)]))
    if cat == _PAIR and hole[0][0] != hole[1][0] and not {c[0] for c in hole} & {c[0] for c in board}:
        return 0.1
    if cat >= 3:
        return 0.9
    return {0: 0.1, 1: 0.45, 2: 0.75}[cat]


class PersonaAgent(Agent):
    def __init__(self, params: PersonaParams, rng: np.random.Generator) -> None:
        self.params, self.rng = params, rng

    def act(self, observation: Observation) -> Action:
        if not observation.board:
            return self._preflop(observation)
        return self._postflop(observation)

    def _raise(self, obs: Observation, to: int) -> Action:
        la = obs.legal
        if la.min_raise_to is None:
            return Action("call")
        return Action("raise", int(min(max(to, la.min_raise_to), la.max_raise_to)))

    def _preflop(self, obs: Observation) -> Action:
        p, la = self.params, obs.legal
        pct = hand_top_pct(*(card(c) for c in obs.hole_cards))
        top = max(obs.bets.values(), default=0)
        raises = sum(1 for _, k, _ in obs.action_history if k == "cbr")
        if pct < p.pfr and raises < MAX_PREFLOP_RAISES:
            return self._raise(obs, 3 * max(top, obs.bb))
        if pct < p.vpip + BB_CHECK_COMP * (p.vpip - p.pfr):
            return Action("call")
        return Action("fold") if la.call_amount > 0 and la.can_fold else Action("call")

    def _postflop(self, obs: Observation) -> Action:
        p, la = self.params, obs.legal
        s = _strength(obs.hole_cards, obs.board)
        g = min(1.0, p.aggression * (0.6 + 0.8 * s))  # chance to bet or raise
        if la.call_amount == 0:
            if self.rng.random() < g:
                return self._raise(obs, max(obs.bb, int(obs.pot * (0.5 + 0.5 * s))))
            return Action("call")
        if la.can_fold and self.rng.random() < p.fold_to_bet * (1.0 - s):
            return Action("fold")
        if self.rng.random() < g * 0.5 * s:
            return self._raise(obs, max(obs.bets.values(), default=0) + int(obs.pot * 0.75))
        return Action("call")
