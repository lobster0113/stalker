"""E2 engine vs PokerKit, chip for chip (#177 review: the ADR 0012 E2-0 independent cross-check).

Random E2 hands are replayed in PokerKit with the same hole cards and board. After every action the
two engines must agree on the stacks, who acts next and the street; at the end on each player's
result (fold wins, uncalled-chip returns, showdown splits). PokerKit is the same independent rules
engine the tournament simulator is checked against (Gate R).
"""
import numpy as np
import pytest
from pokerkit import Automation as A
from pokerkit import NoLimitTexasHoldem

from stalker.core.cards import card_str
from stalker.e2 import game as G

AUTO = (A.ANTE_POSTING, A.BET_COLLECTION, A.BLIND_OR_STRADDLE_POSTING, A.CARD_BURNING,
        A.RUNOUT_COUNT_SELECTION, A.HOLE_CARDS_SHOWING_OR_MUCKING, A.HAND_KILLING, A.CHIPS_PUSHING,
        A.CHIPS_PULLING)
PK = {0: 1, 1: 0}  # heads-up PokerKit index 0 is the big blind; E2 player 0 is the small blind/button


def _pk_state(s0: G.State):
    st = NoLimitTexasHoldem.create_state(AUTO, True, 0, (G.SB, G.BB), G.BB, (G.STACK, G.STACK), 2)
    # PokerKit deals hole cards one at a time, player 0 first, two rounds.
    for rnd in range(2):
        for pk in (0, 1):
            st.deal_hole(card_str(s0.hole[1 - pk][rnd]))
    return st


def _deal_boards(st, board_cards: list[int], dealt: int) -> int:
    while st.can_deal_board():
        k = 3 if dealt == 0 else 1
        st.deal_board("".join(card_str(c) for c in board_cards[dealt:dealt + k]))
        dealt += k
    return dealt


def _replay(rng):
    s = G.deal(rng)
    full_board = list(s.deck[:5])
    st = _pk_state(s)
    dealt = 0
    while not s.done:
        assert st.actor_index == PK[s.to_act], (s.history, st.actor_index)
        acts = G.legal(s)
        a = acts[int(rng.integers(len(acts)))]
        ns = G.apply(s, a)
        if a == "f":
            st.fold()
        elif a in ("c", "k"):
            st.check_or_call()
        else:
            p = s.to_act  # raise-to = this street's total for p (ns.bet resets if the street closed)
            st.complete_bet_or_raise_to(ns.total[p] - (s.total[p] - s.bet[p]))
        s = ns
        dealt = _deal_boards(st, full_board, dealt)
        if not s.done:
            for p in (0, 1):
                assert st.stacks[PK[p]] == s.stack[p], (s.history, p)
    dealt = _deal_boards(st, full_board, dealt)
    return s, st


@pytest.mark.parametrize("seed", range(4))
def test_random_hands_match_pokerkit_chip_for_chip(seed):
    rng = np.random.default_rng(1000 + seed)
    for _ in range(500):
        s, st = _replay(rng)
        assert not st.status, "PokerKit hand should be over"
        pay = G.payoff(s)
        assert st.stacks[PK[0]] - G.STACK == pay and st.stacks[PK[1]] - G.STACK == -pay, (s.history, st.stacks)
