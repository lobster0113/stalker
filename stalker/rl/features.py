"""HeroObservation -> fixed-size numpy features for the RL policy (no torch import, so it is testable anywhere).

Only fields of the observation contract (docs/OBSERVATION.md) are read; `validate_observation` rejects
anything else, so a leak (e.g. an extra `deck` key) fails loudly instead of being silently ignored.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np

from stalker.observe.builder import MAX_SEATS, HeroObservation, SeatToken
from stalker.observe.memory import CONTEXTS

RANKS, SUITS = "23456789TJQKA", "cdhs"
N_CARD_SLOTS = 7  # 2 hole + 5 board
CARD_DIM = 17  # rank one-hot + suit one-hot
ACTIONS = ("f", "c", "r")
HERO_KEYS = frozenset(f.name for f in dataclasses.fields(HeroObservation))
SEAT_KEYS = frozenset(f.name for f in dataclasses.fields(SeatToken))
LEGAL_KEYS = frozenset({
    "fold", "call", "raise", "call_amount", "call_amount_bb", "min_raise_to", "max_raise_to",
    "min_raise_to_bb", "max_raise_to_bb"})
TOURNAMENT_KEYS = frozenset({
    "level_index", "blinds", "next_blinds", "players_total", "players_remaining", "paid_places", "prizes", "buy_in",
    "avg_stack", "avg_stack_bb", "hero_rank", "stack_quantiles_bb", "stack_quantiles"})
STATS_KEYS = frozenset(CONTEXTS) | {"vpip_hands", "pfr_hands", "showdowns"}

# seat token: 5 flags + 2 log-sizes + 4 ctx x 3 action rates + 4 ctx log-opportunities + 4 rate/hands summaries
SEAT_STAT_DIM = len(CONTEXTS) * 3 + len(CONTEXTS) + 4
SEAT_DIM = 7 + SEAT_STAT_DIM
GLOBAL_DIM = 8 + 9 + 4 + 5  # table state, stack quantiles, legal amounts, last-action summary


def _check(name: str, got, allowed: frozenset) -> None:
    extra = set(got) - allowed
    if extra:
        raise ValueError(f"{name} has fields outside the observation contract: {sorted(extra)}. See docs/OBSERVATION.md.")


def validate_observation(obs: HeroObservation) -> None:
    if not isinstance(obs, HeroObservation):
        raise TypeError(f"policy input must be a HeroObservation from ObservationBuilder, got {type(obs).__name__}.")
    if len(obs.seats) != MAX_SEATS:
        raise ValueError(f"seats must have {MAX_SEATS} slots, got {len(obs.seats)}.")
    _check("legal", obs.legal, LEGAL_KEYS)
    _check("tournament", obs.tournament, TOURNAMENT_KEYS)
    for s in obs.seats:
        if not isinstance(s, SeatToken):
            raise TypeError("seats must be SeatToken instances.")
        if s.stats is not None:
            _check("seat stats", s.stats, STATS_KEYS)


def _log(x: float) -> float:
    return math.log1p(max(x, 0.0)) / 4.0


def _card(vec: np.ndarray, card: str) -> None:
    vec[RANKS.index(card[0])] = 1.0
    vec[13 + SUITS.index(card[1])] = 1.0


def _seat_features(s: SeatToken, with_stats: bool) -> np.ndarray:
    v = np.zeros(SEAT_DIM, dtype=np.float32)
    if not s.used:
        return v
    v[:7] = (s.is_hero, s.is_button, s.in_hand, s.all_in, 1.0, _log(s.stack_bb), _log(s.bet_bb))
    if with_stats and s.stats is not None:
        i, hands = 7, max(s.hands_seen, 1)
        for c in CONTEXTS:
            st = s.stats[c]
            opp = max(st["opportunities"], 1)
            v[i:i + 3] = [st[a] / opp for a in ACTIONS]
            i += 3
        for c in CONTEXTS:
            v[i] = _log(s.stats[c]["opportunities"])
            i += 1
        v[i:i + 4] = (s.stats["vpip_hands"] / hands, s.stats["pfr_hands"] / hands, s.stats["showdowns"] / hands,
                      _log(s.hands_seen))
    return v


def encode(obs: HeroObservation, with_stats: bool = True) -> dict[str, np.ndarray]:
    """Features: seats (9, SEAT_DIM), seat_mask (9,) True = real seat, cards (7, CARD_DIM), card_mask (7,), glob (GLOBAL_DIM,)."""
    validate_observation(obs)
    seats = np.stack([_seat_features(s, with_stats) for s in obs.seats])
    cards = np.zeros((N_CARD_SLOTS, CARD_DIM), dtype=np.float32)
    card_mask = np.zeros(N_CARD_SLOTS, dtype=bool)
    for i, c in enumerate(tuple(obs.hole_cards) + tuple(obs.board)):
        _card(cards[i], c)
        card_mask[i] = True
    t, lg = obs.tournament, obs.legal
    bb = t["blinds"]["bb"]
    n_raises = sum(1 for _, a, _ in obs.history if a == "cbr")
    glob = np.zeros(GLOBAL_DIM, dtype=np.float32)
    glob[:8] = (
        _log(obs.pot_bb), t["players_remaining"] / t["players_total"], t["paid_places"] / t["players_total"],
        _log(t["avg_stack_bb"]), (t["hero_rank"] - 1) / max(t["players_total"] - 1, 1), t["blinds"]["ante"] / bb,
        t["level_index"] / 20.0, (t["prizes"][0] / t["buy_in"]) / t["players_total"] if t["prizes"] else 0.0)
    glob[8:17] = [_log(x) for x in t["stack_quantiles_bb"]]
    glob[17:21] = (_log(lg["call_amount_bb"]), _log(lg["min_raise_to_bb"]), _log(lg["max_raise_to_bb"]),
                   float(lg["fold"]))
    glob[21:26] = (n_raises / 4.0, len(obs.history) / 20.0, len(obs.board) / 5.0,
                   sum(s.in_hand for s in obs.seats if s.used) / MAX_SEATS, float(lg["raise"]))
    return {"seats": seats, "seat_mask": np.array([s.used for s in obs.seats]), "cards": cards,
            "card_mask": card_mask, "glob": glob}
