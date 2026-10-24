"""Fast NLHE hand engine: a lean pure-Python replica of the PokerKit rules `Hand` uses (ADR 0005).

Drop-in for `stalker.tournament.hand.Hand` (same constructor, actions, `legal_actions`, `result`), built for
RL rollouts and large evaluations. PokerKit stays the rule oracle: `tests/test_fast_hand.py` replays the
same cards and actions through both engines and requires identical legal-action sets and `HandResult`s.

Rules mirrored from PokerKit 0.7.7 (tournament mode, no ante trimming) because they are not textbook-obvious:
- Antes are dead money in the lowest pot; a player all-in from the ante stays eligible for all of it.
- Blinds are capped by the stack left after the ante. Heads-up the button posts the SB and the other
  seat posts the BB (and the BB ante).
- Betting opens left of the largest posted blind; a player whose stack cannot be called by any other
  live player (effective stack 0) does not act. A short all-in raise does not reopen betting for players
  who already acted, until short all-ins add up to a full raise.
- Uncalled chips above the second-largest bet are returned when the street's bets are collected.
- At showdown, hands that cannot win any pot are killed before pots are rebuilt and pushed, so adjacent
  pots with the same surviving eligible set merge; odd chips go to the first winner in action order
  (left of the button).
Cards come from the same `rng.permutation(52)` deck in the same draw order (hole cards round-robin from
the seat left of the button, burn before each street), so a same-seed `Hand` deals identical cards.
"""
from __future__ import annotations

from collections import deque
from typing import Sequence

import numpy as np

from stalker.core.cards import N_CARDS, card_str
from stalker.core.evaluator import evaluate
from stalker.tournament.hand import ANTE_MODES, AnteMode, HandResult, LegalActions, Pot, PotAward

_RIVER = 3


class FastHand:
    """One NLHE hand with `Hand`'s interface. Act via `fold` / `check_or_call` / `raise_to` until `is_over`."""

    __slots__ = (
        "seats", "_index", "n_seats", "button", "starting_stacks", "_n", "_bb", "_hole", "_board",
        "_stacks", "_bets", "_live", "_paid", "_antes", "_street", "_actors", "_acted", "_raise_amt",
        "_short_allins", "_all_in", "_over", "_pots", "_awards", "_actions",
    )

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
        self.seats: tuple[int, ...] = tuple(s for s in order if stacks[s] > 0)  # index -> seat
        n = len(self.seats)
        if n < 2:
            raise ValueError("a hand needs at least 2 occupied seats")
        if 2 * n + 8 > N_CARDS:
            raise ValueError(f"{n} players need more than {N_CARDS} cards")
        self._index = {seat: i for i, seat in enumerate(self.seats)}
        self.n_seats = n_seats
        self.button = button
        self.starting_stacks = tuple(stacks)
        self._n = n
        self._bb = big_blind

        # Draw k is deck[-1 - k]: hole cards round-robin (2n), then burn+flop, burn+turn, burn+river.
        deck = rng.permutation(N_CARDS).tolist()
        top = N_CARDS - 1
        self._hole = [(deck[top - i], deck[top - n - i]) for i in range(n)]
        b = top - 2 * n
        self._board = [deck[b - 1], deck[b - 2], deck[b - 3], deck[b - 5], deck[b - 7]]

        st = [stacks[s] for s in self.seats]
        heads_up = n == 2
        # Antes: index 1 is the BB for n > 2; heads-up the BB is index 0.
        if ante_mode == "classic":
            antes = [min(ante, s) for s in st]
        elif ante_mode == "bb_ante":
            antes = [0] * n
            bb_i = 0 if heads_up else 1
            antes[bb_i] = min(ante, st[bb_i])
        else:
            antes = [0] * n
        blinds = [0] * n
        if heads_up:
            blinds[0], blinds[1] = big_blind, small_blind
        else:
            blinds[0], blinds[1] = small_blind, big_blind
        bets = [0] * n
        for i in range(n):
            st[i] -= antes[i]
            posted = min(blinds[i], st[i])
            bets[i] = posted
            st[i] -= posted
        self._stacks = st
        self._bets = bets
        self._antes = antes
        self._paid = [antes[i] + bets[i] for i in range(n)]  # chips put in this hand (net of refunds)
        self._live = [True] * n
        self._street = 0
        self._all_in = False
        self._over = False
        self._pots: tuple[Pot, ...] = ()
        self._awards: tuple[PotAward, ...] = ()
        self._actions: list[tuple[int, str, int]] = []
        self._acted: set[int] = set()
        self._short_allins: list[int] = []
        self._raise_amt = 0

        # Preflop opener: left of the largest posted blind (ties -> later index), as PokerKit.
        best = max(range(n), key=lambda i: (bets[i] if blinds[i] else 0, i))
        self._begin_betting((best + 1) % n)

    # --- betting -----------------------------------------------------------------------------------

    def _begin_betting(self, opener: int) -> None:
        n, st, bets, live = self._n, self._stacks, self._bets, self._live
        totals = sorted(bets[i] + st[i] for i in range(n) if live[i])
        second = totals[-2]
        actors = deque()
        for k in range(n):
            i = (opener + k) % n
            if live[i] and st[i] and min(st[i], max(0, second - bets[i])):
                actors.append(i)
        self._actors = actors
        self._raise_amt = 0
        self._acted.clear()
        self._short_allins.clear()
        if not actors or (len(actors) == 1 and bets[actors[0]] >= max(bets)):
            self._end_betting()

    def _after_action(self) -> None:
        if not self._actors or self._live.count(True) <= 1:
            self._end_betting()

    def _end_betting(self) -> None:
        self._actors.clear()
        n, st, bets, live = self._n, self._stacks, self._bets, self._live
        n_live = live.count(True)
        if n_live > 1 and sum(1 for i in range(n) if live[i] and st[i]) <= 1:
            self._all_in = True
        if self._street == _RIVER and not all(st):
            self._all_in = True
        winner = -1
        held = 0
        if any(bets):
            if n_live == 1:
                winner = live.index(True)
                others = [i for i in range(n) if i != winner]
            else:
                others = range(n)
            cutoff = sorted(bets)[-2]
            for i in others:
                if bets[i] > cutoff:
                    over = bets[i] - cutoff
                    st[i] += over
                    self._paid[i] -= over
                bets[i] = 0
            if winner >= 0:  # the folded-to player's bet stays out of the pots and goes back to them
                held = bets[winner]
                st[winner] += held
                self._paid[winner] -= held
                bets[winner] = 0
        if n_live == 1:
            self._finish_folded(held)
        elif self._street == _RIVER or self._all_in:
            self._showdown()
        else:
            self._street += 1
            self._begin_betting(0)

    # --- settlement --------------------------------------------------------------------------------

    def _build_pots(self, eligible: list[bool], held: int = 0, holder: int = -1) -> list[tuple[int, tuple[int, ...]]]:
        """PokerKit's pot construction: antes seed the lowest pot; equal adjacent eligible sets merge.

        `held` is the uncollected last bet of a folded-to `holder`: outside the pots, but it still counts
        toward which levels the holder is eligible for.
        """
        n, paid, antes = self._n, self._paid, self._antes
        contrib = [paid[i] - antes[i] for i in range(n)]
        pending = list(contrib)
        if holder >= 0:
            pending[holder] += held
        amount = sum(antes)
        prev = 0
        pots: list[tuple[int, tuple[int, ...]]] = []
        for level in sorted(set(contrib)):
            amount += (level - prev) * sum(1 for c in contrib if c >= level)
            players = tuple(i for i in range(n) if pending[i] >= level and eligible[i])
            while pots and pots[-1][1] == players:
                amount += pots.pop()[0]
            if amount:
                pots.append((amount, players))
            amount = 0
            prev = level
        return pots

    def _to_pots(self, pots) -> tuple[Pot, ...]:
        seats = self.seats
        return tuple(Pot(a, tuple(seats[i] for i in p)) for a, p in pots)

    def _finish_folded(self, held: int) -> None:
        pots = self._build_pots(self._live, held, self._live.index(True))
        self._pots = self._to_pots(pots)
        awards = []
        for amount, players in pots:
            (w,) = players
            self._stacks[w] += amount
            awards.append(PotAward(amount, {self.seats[w]: amount}))
        self._awards = tuple(awards)
        self._over = True

    def _showdown(self) -> None:
        n, live = self._n, self._live
        self._pots = self._to_pots(self._build_pots(live))
        board = self._board
        score = [evaluate((*self._hole[i], *board)) if live[i] else -1 for i in range(n)]
        pots = self._build_pots(live)
        # Kill hands that cannot win a share of any pot they are eligible for.
        alive = list(live)
        for i in range(n):
            if live[i] and not any(i in p and score[i] >= max(score[j] for j in p) for _, p in pots):
                alive[i] = False
        awards = []
        seats, st = self.seats, self._stacks
        for amount, players in self._build_pots(alive):
            top = max(score[j] for j in players)
            winners = [j for j in players if score[j] == top]
            q, r = divmod(amount, len(winners))
            won = {}
            for k, j in enumerate(winners):
                share = q + r if k == 0 else q
                st[j] += share
                if share:
                    won[seats[j]] = share
            awards.append(PotAward(amount, won))
        self._awards = tuple(awards)
        self._street = _RIVER
        self._over = True

    # --- public interface (mirrors Hand) -----------------------------------------------------------

    @property
    def is_over(self) -> bool:
        return self._over

    @property
    def actor(self) -> int | None:
        return self.seats[self._actors[0]] if self._actors else None

    def _can_raise(self, i: int, to_call: int, max_bet: int) -> bool:
        st, bets = self._stacks, self._bets
        if to_call < self._raise_amt:
            return False
        if self._short_allins and sum(self._short_allins) < self._raise_amt and i in self._acted:
            return False
        if st[i] <= max_bet - bets[i]:
            return False
        live = self._live
        return any(j != i and live[j] and st[j] + bets[j] > max_bet for j in range(self._n))

    def legal_actions(self) -> LegalActions:
        if not self._actors:
            raise RuntimeError("no player to act (hand is over)")
        i = self._actors[0]
        st, bets = self._stacks[i], self._bets[i]
        max_bet = max(self._bets)
        to_call = min(st, max_bet - bets)
        if self._can_raise(i, to_call, max_bet):
            lo = min(st + bets, max(self._raise_amt, self._bb) + max_bet)
            hi = st + bets
        else:
            lo = hi = None
        return LegalActions(seat=self.seats[i], can_fold=bets < max_bet, call_amount=to_call,
                            min_raise_to=lo, max_raise_to=hi)

    def fold(self) -> None:
        if not self._actors:
            raise RuntimeError("no player to act (hand is over)")
        i = self._actors[0]
        if self._bets[i] >= max(self._bets):
            raise ValueError("fold() illegal: nothing to call; use check_or_call()")
        self._actors.popleft()
        self._acted.add(i)
        self._live[i] = False
        self._actions.append((self.seats[i], "f", 0))
        self._after_action()

    def check_or_call(self) -> None:
        if not self._actors:
            raise RuntimeError("no player to act (hand is over)")
        i = self._actors.popleft()
        self._acted.add(i)
        amount = min(self._stacks[i], max(self._bets) - self._bets[i])
        self._bets[i] += amount
        self._stacks[i] -= amount
        self._paid[i] += amount
        self._actions.append((self.seats[i], "cc", amount))
        self._after_action()

    def raise_to(self, amount: int) -> None:
        """Bet/raise to `amount` total chips this street. Must be within legal_actions() bounds."""
        la = self.legal_actions()
        if la.min_raise_to is None or not la.min_raise_to <= amount <= la.max_raise_to:
            raise ValueError(
                f"raise_to({amount}) illegal: allowed {la.min_raise_to}..{la.max_raise_to}; check legal_actions()"
            )
        amount = int(amount)
        n, st, bets, live = self._n, self._stacks, self._bets, self._live
        i = self._actors.popleft()
        self._acted.add(i)
        raise_by = amount - max(bets)
        delta = amount - bets[i]
        bets[i] = amount
        st[i] -= delta
        self._paid[i] += delta
        self._actors = deque(j for j in ((i + k) % n for k in range(1, n)) if live[j] and st[j])
        if raise_by >= self._raise_amt:
            self._acted.clear()
            self._acted.add(i)
        self._raise_amt = max(self._raise_amt, raise_by)
        if st[i]:
            self._short_allins.clear()
        else:
            self._short_allins.append(raise_by)
        if sum(self._short_allins) >= self._raise_amt:
            self._short_allins.clear()
        self._actions.append((self.seats[i], "cbr", amount))
        self._after_action()

    def hole_cards(self, seat: int) -> list[str]:
        return [card_str(c) for c in self._hole[self._index[seat]]]

    def hole_card_ints(self, seat: int) -> tuple[int, int]:
        return self._hole[self._index[seat]]

    def board(self) -> list[str]:
        return [card_str(c) for c in self._board[:self._board_count()]]

    def _board_count(self) -> int:
        return (0, 3, 4, 5)[self._street]

    def actions(self) -> list[tuple[int, str, int]]:
        """Player actions so far as (seat, 'f'|'cc'|'cbr', amount) — replayable on a same-seed hand."""
        return list(self._actions)

    def result(self) -> HandResult:
        if not self._over:
            raise RuntimeError("hand not finished; keep acting until is_over")
        final = list(self.starting_stacks)
        for i, seat in enumerate(self.seats):
            final[seat] = self._stacks[i]
        return HandResult(
            starting_stacks=self.starting_stacks,
            final_stacks=tuple(final),
            deltas=tuple(f - s for f, s in zip(final, self.starting_stacks)),
            pots=self._pots,
            awards=self._awards,
        )
