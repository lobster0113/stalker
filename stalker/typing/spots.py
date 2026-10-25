"""Spot keys: the cell a decision belongs to (stage, effective stack, position, street, pot type, opponents).

A cell is the unit the data-sufficiency criteria (referee/DATA_SUFFICIENCY.md) are applied to, so the key is
computed only from fields of the decision record, never from the hidden deal. `spot_key` returns None for a
decision it cannot place; the report counts those instead of hiding them.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Sequence

from stalker.records.schema import ActionOption, DecisionRecord

STAGES = ("early", "mid", "bubble", "itm", "final")
STACK_EDGES_BB = (5.0, 10.0, 15.0, 25.0, 40.0)
STACK_LABELS = ("<5", "5-10", "10-15", "15-25", "25-40", "40+")
POSITIONS = ("BTN", "SB", "BB", "UTG", "MP", "HJ", "CO")
POT_TYPES = ("unopened", "facing_open", "facing_3bet+", "facing_bet", "facing_allin")
PROFILES = ("unknown", "tight", "normal", "loose")
ACTION_CATEGORIES = ("fold", "call", "raise", "allin")

EARLY_SHARE = 0.7  # at least this share of the field still in: early, otherwise mid
MIN_PROFILE_HANDS = 10  # hands of memory before an opponent profile is trusted
TIGHT_VPIP, LOOSE_VPIP = 0.25, 0.40


@dataclass(frozen=True)
class SpotKey:
    stage: str
    stack_bb: str
    position: str
    street: str
    pot_type: str
    profile: str

    def label(self) -> str:
        return "|".join((self.stage, self.stack_bb, self.position, self.street, self.pot_type, self.profile))


def position_label(seats: Sequence[int], button: int, hero_seat: int) -> str:
    """Position of `hero_seat` among the occupied `seats` (clockwise order = ascending seat number)."""
    order = sorted(seats)
    if hero_seat not in order or button not in order:
        return "?"
    n = len(order)
    rel = (order.index(hero_seat) - order.index(button)) % n
    if n == 2:
        return "BTN" if rel == 0 else "BB"  # the button posts the small blind heads-up
    if rel < 3:
        return ("BTN", "SB", "BB")[rel]
    j, k = rel - 3, n - 3  # j-th of the k players between the big blind and the button
    if j == k - 1:
        return "CO"
    if j == k - 2:
        return "HJ"
    return "UTG" if j == 0 else "MP"


def stack_bucket(stack_bb: float) -> str:
    return STACK_LABELS[bisect.bisect_right(STACK_EDGES_BB, stack_bb)]


def _stage(remaining: int, paid_places: int, table_size: int, players: int) -> str:
    if remaining <= paid_places:
        return "itm"
    if remaining == paid_places + 1:
        return "bubble"
    if players > table_size and remaining <= table_size:
        return "final"
    return "early" if remaining >= EARLY_SHARE * players else "mid"


def _profile(r: DecisionRecord) -> str:
    m = r.session_memory_snapshot
    if m is None or m.hands_observed < MIN_PROFILE_HANDS or "opp_vpip" not in m.features:
        return "unknown"
    v = m.features["opp_vpip"]
    return "tight" if v < TIGHT_VPIP else "loose" if v > LOOSE_VPIP else "normal"


def spot_key(r: DecisionRecord, players: int | None = None) -> SpotKey | None:
    """`players` = tournament field size (stage detection); defaults to the table size."""
    ob, tc = r.table_observation, r.tournament_context
    hero = next((s for s in ob.seats if s.seat == ob.hero_seat), None)
    if hero is None or tc.bb <= 0 or ob.position not in POSITIONS or ob.street not in ("preflop", "flop", "turn", "river"):
        return None
    others = [s for s in ob.seats if s.in_hand and s.seat != ob.hero_seat]
    own = hero.stack + hero.bet
    eff = min(own, max((s.stack + s.bet for s in others), default=own))
    top_bet = max((s.bet for s in ob.seats), default=0)
    call = max(top_bet - hero.bet, 0)
    if call > 0 and call >= hero.stack:
        pot = "facing_allin"
    elif ob.street == "preflop":
        raises = sum(1 for a in ob.current_hand_actions if a.kind == "cbr")
        pot = "unopened" if raises == 0 else "facing_open" if raises == 1 else "facing_3bet+"
    else:
        pot = "facing_bet" if call > 0 else "unopened"
    stage = _stage(tc.remaining, tc.paid_places, tc.table_size, players or tc.table_size)
    return SpotKey(stage, stack_bucket(eff / tc.bb), ob.position, ob.street, pot, _profile(r))


def action_category(option: ActionOption, hero_stack_plus_bet: int) -> str:
    if option.kind != "raise":
        return option.kind
    return "allin" if option.amount >= hero_stack_plus_bet else "raise"


def category_probs(r: DecisionRecord) -> dict[str, float]:
    """The record's `probs_ai0` summed per action category (fold / call / raise / allin)."""
    ob = r.table_observation
    hero = next(s for s in ob.seats if s.seat == ob.hero_seat)
    out = dict.fromkeys(ACTION_CATEGORIES, 0.0)
    for option, p in zip(ob.action_space, r.probs_ai0):
        out[action_category(option, hero.stack + hero.bet)] += p
    return out
