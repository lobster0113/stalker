"""The three information contracts (docs/TP.md §2) and DecisionContext (§1.1).

- `PublicObservation`: what the hero may know — the `HeroObservation` built by
  `stalker.observe.builder` (own hole cards + public info; Gate L3 scans it for leaks).
- `TeacherContext`: offline assumptions for answer labels — the assumed opponent policy and
  simulator settings. Never the real hidden cards.
- `PrivateWorldState`: engine-only — other players' hole cards, deck, RNG state.

A function that takes a `TeacherContext` must not take a `PrivateWorldState` (tests scan every
signature): answers are conditional on public information and stated assumptions only, so swapping
hidden cards cannot change them (Gate L7).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from stalker.observe.builder import HeroObservation

DECISION_CONTEXT_VERSION = "0.1"
STREETS = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}

PublicObservation = HeroObservation


@dataclass(frozen=True)
class TeacherContext:
    opponent_policy_id: str
    opponent_policy_version: str
    # (hand_class, action) -> probability the assumed opponent takes that public action
    opponent_policy: Callable[[str, str], float]
    simulator: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PrivateWorldState:
    hole_cards: dict[int, tuple[str, str]]  # seat -> cards, other players included
    deck: tuple[str, ...]
    rng_state: Any = None


@dataclass(frozen=True)
class DecisionContext:
    """Facts the action head may read directly (docs/TP.md §1.1). Chips are in big blinds.

    Positions count seats after the button among occupied seats (0 = button, 1 = SB, 2 = BB).
    `street_aggressor` is known preflop only: the public history has no street markers yet, so
    postflop it is None rather than a guess.
    """

    street: str
    hero_position: str
    position_vs_button: int
    opponents_to_act: int
    opponent_positions: tuple[int, ...]
    street_aggressor: int | None
    preflop_aggressor: int | None
    legal_actions: tuple[str, ...]
    to_call: float
    min_raise: float
    max_raise: float
    pot: float
    effective_stack_bb: float
    spr: float
    required_equity: float
    all_in: bool
    board: tuple[str, ...]
    hole_cards: tuple[str, ...]
    tournament_public_summary: dict
    decision_context_version: str = DECISION_CONTEXT_VERSION


def _position_label(d: int, n: int) -> str:
    """TP §6 position buckets: blinds / early / middle / late (CO, BTN)."""
    if n == 2:
        return "blinds" if d in (0, 1) else "late"
    if d in (1, 2):
        return "blinds"
    if d == 0 or d == n - 1:
        return "late"
    return "early" if d - 2 <= (n - 3) // 2 else "middle"


def decision_context(po: PublicObservation) -> DecisionContext:
    used = [k for k, s in enumerate(po.seats) if s.used]
    n = len(used)
    button = next(k for k, s in enumerate(po.seats) if s.used and s.is_button)
    order = used[used.index(button):] + used[:used.index(button)]
    pos = {slot: order.index(slot) for slot in used}
    hero = po.seats[0]
    opps = [k for k in used if k != 0 and po.seats[k].in_hand]
    active = [k for k in opps if not po.seats[k].all_in]
    raises = [slot for slot, a, _ in po.history if a == "cbr"]
    preflop = not po.board
    lg = po.legal
    to_call = lg["call_amount_bb"]
    deepest_opp = max((po.seats[k].stack_bb + po.seats[k].bet_bb for k in opps), default=0.0)
    eff = min(hero.stack_bb + hero.bet_bb, deepest_opp)
    t = po.tournament
    return DecisionContext(
        street=STREETS[len(po.board)],
        hero_position=_position_label(pos[0], n),
        position_vs_button=pos[0],
        opponents_to_act=len(active),
        opponent_positions=tuple(pos[k] for k in active),
        street_aggressor=(pos[raises[-1]] if raises else None) if preflop else None,
        preflop_aggressor=(pos[raises[-1]] if raises else None) if preflop else None,
        legal_actions=tuple(a for a in ("fold", "call", "raise") if lg[a]),
        to_call=to_call,
        min_raise=lg["min_raise_to_bb"],
        max_raise=lg["max_raise_to_bb"],
        pot=po.pot_bb,
        effective_stack_bb=eff,
        spr=eff / po.pot_bb if po.pot_bb else 0.0,
        required_equity=to_call / (po.pot_bb + to_call) if to_call > 0 else 0.0,
        all_in=any(po.seats[k].all_in for k in used if po.seats[k].in_hand),
        board=po.board,
        hole_cards=po.hole_cards,
        tournament_public_summary={
            "total_entries": t["players_total"], "remaining_players": t["players_remaining"],
            "paid_places": t["paid_places"], "payout_vector": t["prizes"], "blind_level": t["level_index"],
            "next_blind_change": t["next_blinds"], "hero_rank": t["hero_rank"],
            "stack_distribution_deciles": t["stack_quantiles_bb"],
        },
    )
