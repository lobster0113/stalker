"""Observation Builder: the only way information reaches an AI policy (contract in docs/OBSERVATION.md).

Input is the director's per-decision `Observation` (own hole cards + public info) and the player's
`GameMemory`; output is a plain-data `HeroObservation` with no reference to engine objects, so a
recursive leak scan over it is meaningful. Seats are listed hero-first, clockwise, so the encoding
does not depend on absolute seat numbers.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from stalker.agents.base import Observation
from stalker.observe.memory import CONTEXTS, GameMemory, MemoryBoundaryError
from stalker.tournament.config import TournamentConfig

MAX_SEATS = 9
STACK_QUANTILES = tuple(i / 8 for i in range(9))  # fixed-length stack distribution summary (min..max)


@dataclass(frozen=True)
class SeatToken:
    used: bool  # False = no player in this slot (mask)
    is_hero: bool = False
    is_button: bool = False
    in_hand: bool = False
    all_in: bool = False
    stack: int = 0
    stack_bb: float = 0.0
    bet: int = 0
    bet_bb: float = 0.0
    player_id: int = -1  # public identity, keys the opponent memory
    hands_seen: int = 0
    stats: dict | None = None  # per-context {opportunities, f, c, r}, plus vpip/pfr/showdown counts


@dataclass(frozen=True)
class HeroObservation:
    game_id: str
    hand_id: int
    hole_cards: tuple[str, ...]
    board: tuple[str, ...]
    pot: int
    pot_bb: float
    seats: tuple[SeatToken, ...]  # MAX_SEATS slots, hero first
    legal: dict  # masks fold/call/raise + amounts in chips and bb
    history: tuple[tuple[int, str, int], ...]  # this hand, public: (slot relative to hero, 'f'|'cc'|'cbr', amount)
    tournament: dict
    recent_actions: tuple[tuple[int, int, int, str, int], ...]  # (hand_id, player_id, street, action, amount)
    showdowns: tuple[tuple[int, int, tuple[str, ...], tuple[str, ...]], ...]  # public showdowns this game


class ObservationBuilder:
    def __init__(self, config: TournamentConfig) -> None:
        if config.table_size > MAX_SEATS:
            raise ValueError(f"table_size {config.table_size} exceeds the {MAX_SEATS}-seat observation.")
        self.config = config

    def build(self, obs: Observation, memory: GameMemory | None = None) -> HeroObservation:
        if memory is not None and memory.game_id != obs.game_id:
            raise MemoryBoundaryError(f"memory belongs to game {memory.game_id!r}, observation to {obs.game_id!r}.")
        n = self.config.table_size
        bb = obs.bb
        rel = {(obs.seat + k) % n: k for k in range(n)}  # absolute seat -> slot relative to hero
        tokens = [SeatToken(used=False)] * MAX_SEATS
        for seat, stack in obs.stacks.items():
            pid = obs.seat_players[seat]
            bet = obs.bets.get(seat, 0)
            tokens[rel[seat]] = SeatToken(
                used=True, is_hero=seat == obs.seat, is_button=seat == obs.button, in_hand=seat in obs.in_hand,
                all_in=stack == 0 and seat in obs.in_hand, stack=stack, stack_bb=stack / bb, bet=bet, bet_bb=bet / bb,
                player_id=pid, **self._memory_fields(memory, pid, seat == obs.seat))
        la = obs.legal
        legal = {
            "fold": la.can_fold, "call": True, "raise": la.min_raise_to is not None,
            "call_amount": la.call_amount, "call_amount_bb": la.call_amount / bb,
            "min_raise_to": la.min_raise_to or 0, "max_raise_to": la.max_raise_to or 0,
            "min_raise_to_bb": (la.min_raise_to or 0) / bb, "max_raise_to_bb": (la.max_raise_to or 0) / bb,
        }
        hist = tuple((rel[s], a, amt) for s, a, amt in obs.action_history)
        return HeroObservation(
            game_id=obs.game_id, hand_id=obs.hand_id, hole_cards=tuple(obs.hole_cards), board=tuple(obs.board),
            pot=obs.pot, pot_bb=obs.pot / bb, seats=tuple(tokens), legal=legal, history=hist,
            tournament=self._tournament(obs),
            recent_actions=() if memory is None else tuple(
                (a.hand_id, a.player_id, a.street, a.action, a.amount) for a in memory.recent_actions),
            showdowns=() if memory is None else tuple(
                (s.hand_id, s.player_id, s.hole_cards, s.board) for s in memory.showdowns))

    @staticmethod
    def _memory_fields(memory: GameMemory | None, pid: int, is_hero: bool) -> dict:
        if memory is None or is_hero or pid not in memory.opponents:
            return {}
        st = memory.opponents[pid]
        stats = {c: {"opportunities": st.opportunities[c], **st.actions[c]} for c in CONTEXTS}
        stats.update(vpip_hands=st.vpip_hands, pfr_hands=st.pfr_hands, showdowns=st.showdowns)
        return {"hands_seen": st.hands, "stats": stats}

    def _tournament(self, obs: Observation) -> dict:
        cfg, bb = self.config, obs.bb
        if not obs.all_stacks:
            raise ValueError("Observation.all_stacks is empty; the tournament-wide stack distribution is required.")
        stacks = np.array(obs.all_stacks, dtype=float)
        # rank by start-of-round chips on both sides (current stacks already lose blinds/bets); 1 = chip leader
        hero_rank = 1 + int((stacks > obs.hand_start_stack).sum())
        return {
            "level_index": cfg.level_index_for_hand(obs.hand_no),
            "blinds": {"sb": obs.sb, "bb": obs.bb, "ante": obs.ante},
            "next_blinds": obs.next_blinds,
            "players_total": cfg.players,
            "players_remaining": obs.players_remaining,
            "paid_places": obs.paid_places,
            "prizes": tuple(cfg.payout_amounts()),
            "buy_in": cfg.buy_in,
            "avg_stack": float(stacks.mean()),
            "avg_stack_bb": float(stacks.mean()) / bb,
            "hero_rank": hero_rank,
            "stack_quantiles_bb": tuple(float(x) / bb for x in np.quantile(stacks, STACK_QUANTILES)),
            "stack_quantiles": tuple(float(x) for x in np.quantile(stacks, STACK_QUANTILES)),
        }
