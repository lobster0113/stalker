"""Thin NLHE hand wrapper over PokerKit (ADR 0002).

Seats are the caller's table seats (0..n-1); a stack of 0 means the seat is empty. PokerKit indexes
players clockwise starting left of the button (button last), so heads-up index 0 is the BB and the
button posts the SB. All cards are dealt from a deck shuffled by the injected Generator — PokerKit's
own deck (shuffled by the global `random`) is never drawn from, which keeps hands reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from pokerkit import (
    Automation,
    Card,
    CheckingOrCalling,
    ChipsPushing,
    CompletionBettingOrRaisingTo,
    Folding,
    HandHistory,
    Mode,
    NoLimitTexasHoldem,
)

from stalker.core.cards import N_CARDS, card_str

AnteMode = Literal["none", "classic", "bb_ante"]
ANTE_MODES = ("none", "classic", "bb_ante")

_AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.RUNOUT_COUNT_SELECTION,
    Automation.HAND_KILLING,
    Automation.CHIPS_PULLING,
)


@dataclass(frozen=True)
class LegalActions:
    """What the player to act may do. `call_amount` is 0 when checking is possible."""

    seat: int
    can_fold: bool
    call_amount: int
    min_raise_to: int | None  # None when raising is not legal
    max_raise_to: int | None


@dataclass(frozen=True)
class Pot:
    amount: int
    eligible: tuple[int, ...]  # seats that can win it


@dataclass(frozen=True)
class PotAward:
    amount: int
    awards: dict[int, int]  # seat -> chips won from this pot


@dataclass(frozen=True)
class HandResult:
    starting_stacks: tuple[int, ...]  # by seat
    final_stacks: tuple[int, ...]
    deltas: tuple[int, ...]
    pots: tuple[Pot, ...]  # main pot first, then side pots, as built after the last bet
    awards: tuple[PotAward, ...]  # PokerKit pushes; when one hand is left, every pot goes in a single push


def _pk_card(c: int) -> Card:
    (parsed,) = Card.parse(card_str(c))
    return parsed


class Hand:
    """One NLHE hand. Act via `fold` / `check_or_call` / `raise_to` until `is_over`."""

    def __init__(
        self,
        stacks: Sequence[int],
        button: int,
        small_blind: int,
        big_blind: int,
        rng: np.random.Generator,
        ante: int = 0,
        ante_mode: AnteMode = "none",
    ) -> None:
        stacks = [int(s) for s in stacks]
        if any(s < 0 for s in stacks):
            raise ValueError("stacks must be >= 0 (0 = empty seat)")
        if not 0 <= button < len(stacks) or stacks[button] == 0:
            raise ValueError(f"button seat {button} must be an occupied seat")
        if ante_mode not in ANTE_MODES:
            raise ValueError(f"ante_mode must be one of {ANTE_MODES}, got {ante_mode!r}")
        if ante_mode == "none" and ante:
            raise ValueError("ante given with ante_mode='none'; pass ante_mode='classic' or 'bb_ante'")
        if ante_mode != "none" and ante <= 0:
            raise ValueError(f"ante_mode={ante_mode!r} needs ante > 0")
        if not 0 < small_blind <= big_blind:
            raise ValueError("need 0 < small_blind <= big_blind")

        n_seats = len(stacks)
        order = [(button + 1 + k) % n_seats for k in range(n_seats)]
        self.seats: tuple[int, ...] = tuple(s for s in order if stacks[s] > 0)  # pokerkit index -> seat
        n = len(self.seats)
        if n < 2:
            raise ValueError("a hand needs at least 2 occupied seats")
        self._index = {seat: i for i, seat in enumerate(self.seats)}
        self.n_seats = n_seats
        self.button = button
        self.starting_stacks = tuple(stacks)

        if ante_mode == "classic":
            antes: int | dict[int, int] = ante
        elif ante_mode == "bb_ante":
            antes = {1: ante}  # index 1 is the BB for n > 2; heads-up pokerkit swaps it to the BB too
        else:
            antes = 0
        self.game = NoLimitTexasHoldem(
            _AUTOMATIONS, False, antes, (small_blind, big_blind), big_blind, mode=Mode.TOURNAMENT
        )
        self.state = self.game([stacks[s] for s in self.seats], n)
        self._deck = [int(c) for c in rng.permutation(N_CARDS)]
        self._pots: tuple[Pot, ...] = ()
        self._holes: list[list[str]] = [[] for _ in range(n)]  # as dealt: PokerKit forgets mucked hands
        self._advance()

    def _draw(self) -> Card:
        return _pk_card(self._deck.pop())

    def _advance(self) -> None:
        st = self.state
        while True:
            if st.can_deal_hole():
                card = self._draw()
                self._holes[st.hole_dealee_index].append(repr(card))
                st.deal_hole([card])
            elif st.can_burn_card():
                st.burn_card(self._draw())
            elif st.can_deal_board():
                st.deal_board([self._draw() for _ in range(st.board_dealing_count)])
            elif st.can_show_or_muck_hole_cards():
                self._snapshot_pots()  # before mucks drop losers from pot eligibility
                st.show_or_muck_hole_cards()
            elif st.can_push_chips():
                self._snapshot_pots()
                st.push_chips()
            else:
                return

    def _snapshot_pots(self) -> None:
        if not self._pots:
            self._pots = tuple(
                Pot(p.amount, tuple(self.seats[i] for i in p.player_indices)) for p in self.state.pots
            )

    @property
    def is_over(self) -> bool:
        return not self.state.status

    @property
    def actor(self) -> int | None:
        i = self.state.actor_index
        return None if i is None else self.seats[i]

    @property
    def stacks(self) -> dict[int, int]:
        """Chips behind by seat, occupied seats only."""
        return {self.seats[i]: s for i, s in enumerate(self.state.stacks)}

    @property
    def bets(self) -> dict[int, int]:
        """Chips committed this street by seat."""
        return {self.seats[i]: b for i, b in enumerate(self.state.bets)}

    @property
    def pot(self) -> int:
        """All chips in the middle, this street's bets included."""
        return self.state.total_pot_amount

    def hole_cards(self, seat: int) -> list[str]:
        """The seat's dealt cards, also after PokerKit mucked them (a hand can end inside the constructor)."""
        return list(self._holes[self._index[seat]])

    def board(self) -> list[str]:
        return [repr(c) for c in self.state.get_board_cards(0)]

    def legal_actions(self) -> LegalActions:
        st = self.state
        if st.actor_index is None:
            raise RuntimeError("no player to act (hand is over)")
        can_raise = st.can_complete_bet_or_raise_to()
        return LegalActions(
            seat=self.seats[st.actor_index],
            can_fold=st.can_fold(),
            call_amount=st.checking_or_calling_amount,
            min_raise_to=st.min_completion_betting_or_raising_to_amount if can_raise else None,
            max_raise_to=st.max_completion_betting_or_raising_to_amount if can_raise else None,
        )

    def fold(self) -> None:
        self.state.fold()
        self._advance()

    def check_or_call(self) -> None:
        self.state.check_or_call()
        self._advance()

    def raise_to(self, amount: int) -> None:
        """Bet/raise to `amount` total chips this street. Must be within legal_actions() bounds."""
        la = self.legal_actions()
        if la.min_raise_to is None or not la.min_raise_to <= amount <= la.max_raise_to:
            raise ValueError(
                f"raise_to({amount}) illegal: allowed {la.min_raise_to}..{la.max_raise_to}; check legal_actions()"
            )
        self.state.complete_bet_or_raise_to(int(amount))
        self._advance()

    def actions(self) -> list[tuple[int, str, int]]:
        """Player actions so far as (seat, 'f'|'cc'|'cbr', amount) — replayable on a same-seed Hand."""
        out = []
        for op in self.state.operations:
            if isinstance(op, Folding):
                out.append((self.seats[op.player_index], "f", 0))
            elif isinstance(op, CheckingOrCalling):
                out.append((self.seats[op.player_index], "cc", op.amount))
            elif isinstance(op, CompletionBettingOrRaisingTo):
                out.append((self.seats[op.player_index], "cbr", op.amount))
        return out

    def result(self) -> HandResult:
        if not self.is_over:
            raise RuntimeError("hand not finished; keep acting until is_over")
        final = list(self.starting_stacks)
        for i, seat in enumerate(self.seats):
            final[seat] = self.state.stacks[i]
        awards = []
        for op in self.state.operations:
            if isinstance(op, ChipsPushing):
                won = {self.seats[i]: a for i, a in enumerate(op.amounts) if a}
                awards.append(PotAward(amount=sum(op.amounts), awards=won))
        return HandResult(
            starting_stacks=self.starting_stacks,
            final_stacks=tuple(final),
            deltas=tuple(f - s for f, s in zip(final, self.starting_stacks)),
            pots=self._pots,
            awards=tuple(awards),
        )

    def to_phh(self) -> str:
        """PHH text of the hand so far. `seats` are 1-based table seats in PHH player order."""
        hh = HandHistory.from_game_state(
            self.game,
            self.state,
            seats=[s + 1 for s in self.seats],
            seat_count=self.n_seats,
        )
        return hh.dumps()


def parse_phh(text: str) -> HandHistory:
    return HandHistory.loads(text)


def replay_phh_final_stacks(text: str) -> tuple[int, ...]:
    """Final stacks in table-seat order (empty seats 0) after replaying a PHH produced by `to_phh`."""
    hh = parse_phh(text)
    state = None
    for state in hh:
        pass
    if hh.seats is None or hh.seat_count is None:
        raise ValueError("PHH lacks seats/seat_count; only hands exported by Hand.to_phh are supported")
    final = [0] * hh.seat_count
    for i, seat in enumerate(hh.seats):
        final[seat - 1] = state.stacks[i]
    return tuple(final)
