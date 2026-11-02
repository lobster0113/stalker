"""Parameter-driven rule bots ("personas", plan §3.5, ADR 0010): a target style VPIP/PFR/aggression/fold-to-bet.

Preflop the hand's top-fraction rank (`hand_top_pct`, 0 = best) is compared with `pfr` and `vpip`; postflop a coarse
made-hand strength and `aggression` / `fold_to_bet` drive bet, call and fold. The bot reads only its own `Observation`
(own hole cards + public info) and draws from the injected `numpy.random.Generator`, keeps no state across hands.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from stalker.agents.base import Action, Agent, Event, Observation
from stalker.core.cards import card
from stalker.core.evaluator import category, evaluate
from stalker.core.ranges import hand_top_pct

# The big blind's free check is not voluntary, so it costs ~1/6 of the seats (vpip - pfr) of VPIP; loosen the other
# decisions by this share of (vpip - pfr) to hit the target (calibrated on 6-max, `tests/test_persona.py`).
BB_CHECK_COMP = 0.08
MAX_PREFLOP_RAISES = 4  # beyond this a raise-worthy hand just calls, so 3-bet wars end
_WEAK = 0.1  # `_strength` of a hand with nothing (or only a board pair)
_PAIR = 1  # evaluator category: pair (0 = high card, 2 = two pair, 3+ = trips and better)


@dataclass(frozen=True)
class PersonaParams:
    vpip: float  # fraction of hands that voluntarily put chips in preflop
    pfr: float  # fraction of hands raised preflop (<= vpip)
    aggression: float  # postflop (bet+raise)/(bet+raise+call)
    fold_to_bet: float  # tendency to give up a weak hand facing a postflop bet
    # Optional per-street style (population-stats note §7.2). None = unused, the bot behaves exactly as without them.
    cbet_flop: float | None = None  # bet frequency of the preflop aggressor when checked to
    cbet_turn: float | None = None
    cbet_river: float | None = None
    fold_cbet_flop: float | None = None  # fold frequency facing the preflop aggressor's first bet
    fold_cbet_turn: float | None = None
    fold_river: float | None = None  # fold frequency facing a river bet
    river_bluff_share: float | None = None  # share of the river c-bets made with a weak hand

    def __post_init__(self) -> None:
        for name in ("vpip", "pfr", "aggression", "fold_to_bet", "cbet_flop", "cbet_turn", "cbet_river",
                     "fold_cbet_flop", "fold_cbet_turn", "fold_river", "river_bluff_share"):
            v = getattr(self, name)
            if v is not None and not 0.0 <= v <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {v}")
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


def _v2(vpip, pfr, aggression, fold_to_bet, cb, fold, bluff):
    return PersonaParams(vpip, pfr, aggression, fold_to_bet, cb[0], cb[1], cb[2], fold[0], fold[1], fold[2], bluff)


def _weak_mass(vpip: float) -> float:
    """Rough share of postflop decisions made with a `_WEAK` hand; tighter ranges hold fewer (calibrated by tests/test_persona_v2.py)."""
    return min(0.6, 0.35 + vpip)


# Street-level types from note §7.2 (percent / 100). Preflop and aggression/fold_to_bet reuse the PRESETS values of the
# same type; `loose_passive` stands for the table's "LP fish". The pro column says "GTO" for c-bets: [assumption] the
# TAG values, with the table's overfold widths (GTO+3 / +8 / +5) added to TAG's fold rates.
PRESETS_V2: dict[str, PersonaParams] = {
    "nit": _v2(*dataclasses.astuple(PRESETS["nit"])[:4], (0.60, 0.40, 0.30), (0.55, 0.62, 0.65), 0.10),
    "weak_tight": _v2(*dataclasses.astuple(PRESETS["weak_tight"])[:4], (0.55, 0.33, 0.25), (0.55, 0.65, 0.65), 0.08),
    "tag": _v2(*dataclasses.astuple(PRESETS["tag"])[:4], (0.65, 0.48, 0.38), (0.48, 0.50, 0.57), 0.20),
    "lag": _v2(*dataclasses.astuple(PRESETS["lag"])[:4], (0.72, 0.55, 0.45), (0.40, 0.45, 0.50), 0.25),
    "loose_passive": _v2(*dataclasses.astuple(PRESETS["loose_passive"])[:4], (0.45, 0.30, 0.25), (0.38, 0.45, 0.45), 0.10),
    "calling_station": _v2(*dataclasses.astuple(PRESETS["calling_station"])[:4], (0.40, 0.25, 0.20), (0.25, 0.28, 0.30), 0.05),
    "maniac": _v2(*dataclasses.astuple(PRESETS["maniac"])[:4], (0.88, 0.70, 0.60), (0.32, 0.33, 0.35), 0.45),
    "pro": _v2(*dataclasses.astuple(PRESETS["high_stakes_pro"])[:4], (0.65, 0.48, 0.38), (0.51, 0.58, 0.62), 0.20),
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
        self._pf_aggr: int | None = None  # seat of the last preflop raiser in the current hand
        self._first_bettor: dict[int, int] = {}  # street (board size 3/4/5) -> seat of its first bettor

    def observe(self, event: Event) -> None:
        # Per-hand memory for c-bet logic only; the table's public events give the street boundaries that
        # `action_history` lacks. It never touches the rng, so personas without street params are unchanged.
        if event.type == "NEW_HAND":
            self._pf_aggr, self._first_bettor = None, {}
        elif event.type == "ACTION" and event.data["action"] == "raise":
            seat, street = event.data["seat"], event.data["street"]
            if street == 0:
                self._pf_aggr = seat
            else:
                self._first_bettor.setdefault(street, seat)

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
        wm = _weak_mass(p.vpip)
        street = len(obs.board) - 2  # 1 flop, 2 turn, 3 river
        if la.call_amount == 0:
            cb = (p.cbet_flop, p.cbet_turn, p.cbet_river)[street - 1]
            if cb is not None and self._pf_aggr == obs.seat:
                weak = s <= _WEAK
                share = p.river_bluff_share if street == 3 else None
                if share is not None:  # bluffs make up `share` of the bets; the weak mass of hands are weak
                    q = cb * share / wm if weak else cb * (1 - share) / (1 - wm)
                else:
                    q = cb
                if self.rng.random() < min(1.0, q):
                    return self._raise(obs, max(obs.bb, int(obs.pot * (0.5 + 0.5 * s))))
                return Action("call")
            if self.rng.random() < g:
                return self._raise(obs, max(obs.bb, int(obs.pot * (0.5 + 0.5 * s))))
            return Action("call")
        fold = (p.fold_cbet_flop, p.fold_cbet_turn, p.fold_river)[street - 1]
        if street < 3:  # a c-bet: the first bet of the street came from the preflop aggressor
            fold = fold if self._first_bettor.get(len(obs.board)) == self._pf_aggr != obs.seat else None
            # note: also true when facing a re-raise after that first bet, unlike persona_stats' `fcb` (n == 1 only)
        if fold is not None:  # weak hands carry the whole fold frequency, so the mean hits the target
            # past the weak mass (tight ranges hold few weak hands) the surplus is taken from one-pair hands
            q = fold / wm if s <= _WEAK else (fold - wm) / 0.6 if s < 0.75 else 0.0
            if la.can_fold and q > 0 and self.rng.random() < min(1.0, q):
                return Action("fold")
        elif la.can_fold and self.rng.random() < p.fold_to_bet * (1.0 - s):
            return Action("fold")
        if self.rng.random() < g * 0.5 * s:
            return self._raise(obs, max(obs.bets.values(), default=0) + int(obs.pot * 0.75))
        return Action("call")
