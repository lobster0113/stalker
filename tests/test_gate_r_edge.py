"""Gate R edge cases: generator coverage, sensitivity, and hand-checked golden cases (referee/gate_r/edge.py).

Every golden case states its expected result and how it was computed by hand, then requires PokerKit `Hand`,
`FastHand` and the independent model to agree with it.
"""
import dataclasses
from types import SimpleNamespace

import numpy as np
import pytest

from referee.gate_r import edge
from referee.gate_r.checks import _check_ranks, _HandModel
from referee.gate_r.edge import HandCase, run_hand, stack_deck, tally_for_edge
from referee.gate_r.settlement import settle
from stalker.core.cards import cards
from stalker.tournament.director import _Table, rank_busts
from stalker.tournament.fast_hand import FastHand
from stalker.tournament.hand import Hand


def _golden(stacks, button, sb, bb, holes, board, script, ante=0, mode="none"):
    """Play a fully scripted hand on all three implementations; return (record, tally)."""
    n = sum(s > 0 for s in stacks)
    holes = {i: tuple(cards(h)) for i, h in holes.items()}  # index 0 = first occupied seat left of the button
    deck = stack_deck(np.random.default_rng(0), n, holes, cards(board))
    case = HandCase(tuple(stacks), button, sb, bb, ante, mode, tuple(deck), 0, script=tuple(script))
    tally = tally_for_edge()
    rec = run_hand(case, tally, "golden")
    assert tally.failures == [] and tally.passed == tally.total
    assert len(rec.actions) == len(script), f"script must cover every action, played {rec.actions}"
    return rec, tally


CHECK, CALL, ALLIN = ("call", 0), ("call", 0), ("allin", 0)


# ---- generators ----
def test_stacked_deck_deals_requested_cards_on_both_engines():
    holes = {0: tuple(cards("AhKd")), 2: tuple(cards("2c2d"))}
    deck = stack_deck(np.random.default_rng(1), 3, holes, cards("Ts9s8s7s"))
    for cls in (Hand, FastHand):
        h = cls(stacks=[50, 50, 50], button=2, small_blind=1, big_blind=2, rng=edge.StackedDeck(deck))
        assert h.hole_cards(0) == ["Ah", "Kd"] and h.hole_cards(2) == ["2c", "2d"]
        while not h.is_over:
            h.check_or_call()
        assert h.board()[:4] == ["Ts", "9s", "8s", "7s"]


@pytest.mark.parametrize("kind", edge.KINDS)
def test_each_kind_generates_its_situation_and_passes(kind):
    n, tally = edge.run_kind(kind, cases=3)
    assert n == 3, f"{kind}: generator did not produce the situation"
    assert tally.failures == [] and tally.total > 0


def test_engine_disagreement_is_caught(monkeypatch):
    orig = FastHand.result

    def off_by_one(self):  # FastHand moves one chip from the first occupied seat to the next
        r = orig(self)
        fs = list(r.final_stacks)
        i, j = [s for s, c in enumerate(r.starting_stacks) if c > 0][:2]
        fs[i], fs[j] = fs[i] - 1, fs[j] + 1
        return dataclasses.replace(r, final_stacks=tuple(fs))

    monkeypatch.setattr(FastHand, "result", off_by_one)
    _, tally = edge.run_kind("side_pots_split_odd", cases=2)
    passed, total = tally.counts["engines"]
    assert passed < total


def test_wrong_settlement_rule_is_caught(monkeypatch):
    # an independent model that gives odd chips to the last winner must disagree with both engines
    from referee.gate_r import checks

    monkeypatch.setattr(checks, "settle", lambda paid, folded, keys, order, antes=None:
                        settle(paid, folded, keys, list(reversed(order)), antes))
    _, tally = edge.run_kind("side_pots_split_odd", cases=5)
    passed, total = tally.counts["settlement"]
    assert passed < total


# ---- golden cases (hand-computed) ----
def test_golden_short_allin_chain_does_not_reopen():
    # Seats: 0 BTN 40, 1 SB 48, 2 BB 1000, 3 UTG 1000; blinds 5/10. Preflop order 3, 0, 1, 2.
    # 3 opens to 30 (full raise 20). 0 shoves 40 (+10, short), 1 shoves 48 (+8, short; 10+8 = 18 < 20).
    # 2 has not acted, calls 48. 3 acted before the shorts: 18 more is not a full raise -> call/fold only.
    stacks = [40, 48, 1000, 1000]
    holes = {3: "AsAd", 0: "KsKd", 1: "Qh7h", 2: "Jc6d"}  # index 0 = seat 1, 1 = seat 2, 2 = seat 3, 3 = seat 0
    script = [("raise", 30), ALLIN, ALLIN, CALL, CALL] + [CHECK] * 6
    rec, _ = _golden(stacks, 0, 5, 10, holes, "2c5d8h9s3c", script)
    # main 40 x 4 = 160 -> seat 0 (AA); side (48 - 40) x 3 = 24 among 1, 2, 3 -> seat 1 (KK); 2 and 3 keep 952
    assert rec.final == {0: 160, 1: 24, 2: 952, 3: 952}
    for cls in (Hand, FastHand):
        h = cls(stacks=stacks, button=0, small_blind=5, big_blind=10, rng=np.random.default_rng(0))
        h.raise_to(30)
        h.raise_to(40)
        h.raise_to(48)
        h.check_or_call()
        la = h.legal_actions()
        assert la.seat == 3 and la.call_amount == 18 and la.min_raise_to is None


def test_golden_three_side_pots_tie_and_odd_chip():
    # Seats 1..4 hold 11/21/31/41, button 0 holds 100; blinds 1/2. Everyone all-in preflop.
    # Pots: 11 x 5 = 55 (all), 10 x 4 = 40 (2,3,4,0), 10 x 3 = 30 (3,4,0), 10 x 2 = 20 (4,0); 59 of seat 0's
    # 100 is uncalled above 41 and returned. Seats 1, 2 tie (AK); 3, 4 tie (QJ); seat 0 is worst.
    # 55 / 2 = 27 r1: the odd chip goes to seat 1 (first winner left of the button) -> 28, seat 2 27 + 40;
    # 30 / 2 = 15 to seats 3, 4; 20 -> seat 4.
    holes = {0: "AhKd", 1: "AsKc", 2: "QhJd", 3: "QsJc", 4: "7d4s"}
    script = [ALLIN, ALLIN, ALLIN, CALL, CALL]  # order 3, 4, 0, 1, 2
    rec, _ = _golden([100, 11, 21, 31, 41], 0, 1, 2, holes, "2c6h9dTs3c", script)
    assert rec.final == {0: 59, 1: 28, 2: 67, 3: 15, 4: 35}


def test_golden_all_in_from_the_ante_wins_only_the_ante_pot():
    # Classic ante 5, blinds 5/10. Button 0 has 3 chips: all-in from the ante. 1 (SB) and 2 (BB) have 200.
    # Antes 3 + 5 + 5 = 13 are dead money in the lowest pot, which seat 0 contests. 1 limps, 2 checks: 20 more.
    # Seat 0 (AA) wins 13; seat 1 (KK) wins 20 -> 200 - 15 + 20 = 205; seat 2 200 - 15 = 185.
    holes = {0: "KhKd", 1: "QhQd", 2: "AhAd"}
    script = [CALL, CHECK] + [CHECK] * 6
    rec, _ = _golden([3, 200, 200], 0, 5, 10, holes, "2c7d9hJs3s", script, ante=5, mode="classic")
    assert rec.final == {0: 13, 1: 205, 2: 185}


def test_golden_short_big_blind_sets_the_call_amount():
    # Blinds 10/20, BB (seat 2) has 12 and is all-in from the blind. Button 0 must call 12 (the bet made, not
    # the nominal BB), SB 1 completes 2 more. Main pot 36 -> seat 2 (AA). Seats 0 and 1 check down: 488 each.
    holes = {0: "KhKd", 1: "AhAd", 2: "QhQd"}
    script = [CALL, CALL] + [CHECK] * 6
    rec, _ = _golden([500, 500, 12], 0, 10, 20, holes, "2c7d9hJs3s", script)
    assert rec.final == {0: 488, 1: 488, 2: 36}
    for cls in (Hand, FastHand):
        la = cls(stacks=[500, 500, 12], button=0, small_blind=10, big_blind=20, rng=np.random.default_rng(0)).legal_actions()
        assert la.seat == 0 and la.call_amount == 12 and la.min_raise_to == 32  # 12 + max(BB 20, no raise yet)


def test_golden_board_plays_two_way_split_odd_chip():
    # Board T-J-Q-K-A broadway, no flush possible: everyone's best hand is the board.
    # Classic ante 1, blinds 1/2, stacks 101. Button 0 folds; SB 1 completes; BB 2 checks; checked down.
    # Pot 3 antes + 4 = 7 split by seats 1, 2: 3 each, odd chip to seat 1 (left of button).
    holes = {0: "2c3c", 1: "4h5h", 2: "6s7s"}
    script = [("fold", 0), CALL, CHECK] + [CHECK] * 6
    rec, _ = _golden([101, 101, 101], 0, 1, 2, holes, "TsJhQdKcAd", script, ante=1, mode="classic")
    assert rec.final == {0: 100, 1: 102, 2: 101}


def test_golden_wheel_is_the_lowest_straight():
    # Heads-up, button 0 posts SB 1, seat 1 BB 2. Board A-2-3-4-K. Seat 0 holds 5-9: wheel (5-high straight).
    # Seat 1 holds 5-6: 2-3-4-5-6 six-high straight, which beats the wheel. Pot 4 -> seat 1: 52 / 48.
    holes = {0: "5d6h", 1: "5h9s"}  # index 0 = seat 1 (BB), index 1 = seat 0 (button)
    script = [CALL, CHECK] + [CHECK] * 6
    rec, _ = _golden([50, 50], 0, 1, 2, holes, "Ah2d3c4sKd", script)
    assert rec.final == {0: 48, 1: 52}
    assert rec.keys[0] == (4, 3) and rec.keys[1] == (4, 4)


def test_golden_kicker_decides_two_pair():
    # Board A-7-7-2-9. Both hold an ace: aces and sevens; seat 1's queen kicker beats seat 0's jack.
    holes = {0: "AsQd", 1: "AcJd"}
    script = [CALL, CHECK] + [CHECK] * 6
    rec, _ = _golden([50, 50], 0, 1, 2, holes, "Ah7d7c2s9h", script)
    assert rec.final == {0: 48, 1: 52}
    assert rec.keys[1][:3] == rec.keys[0][:3] and rec.keys[1] > rec.keys[0]


def test_golden_uncalled_bet_is_returned():
    # Heads-up, button 0 shoves 100 into seat 1's 40; seat 1 calls 40. 60 is uncalled and returns to seat 0
    # before the showdown. Seat 1 (AA) wins 80: 80 / 60.
    holes = {0: "AhAd", 1: "KhKd"}
    rec, _ = _golden([100, 40], 0, 1, 2, holes, "2c7d9hJs3s", [ALLIN, CALL])
    assert rec.final == {0: 60, 1: 80}


def test_golden_heads_up_transition_button_and_blinds():
    # Three-handed table, last button seat 0; seat 1 busted. The button moves to the next occupied seat (2).
    # Heads-up the button posts the SB and acts first preflop; seat 0 posts the BB.
    t = _Table(0, 3, 0)
    t.seats = [7, None, 9]
    assert t.next_button() == 2
    kw = dict(stacks=[100, 0, 100], button=2, small_blind=5, big_blind=10)
    for cls in (Hand, FastHand):
        la = cls(rng=np.random.default_rng(0), **kw).legal_actions()
        assert la.seat == 2 and la.call_amount == 5 and la.min_raise_to == 20
    d = {"button": 2, "seat_players": {0: 7, 2: 9}, "stacks": {0: 100, 2: 100}, "sb": 5, "bb": 10, "ante": 0}
    m = _HandModel(SimpleNamespace(table_size=3, ante_mode="none"), d, tally_for_edge(), "golden")
    assert (m.sb_seat, m.bb_seat, m.actor) == (2, 0, 2)


def test_golden_simultaneous_busts_rank_by_starting_chips():
    # 6 players left; in one round p3 and p7 bust from 300 chips and p5 from 100. Places 4..6 go to the busted:
    # the two 300s take 4 and 5 (order by a draw), the 100 takes 6.
    order = rank_busts([(3, 300), (5, 100), (7, 300)], np.random.default_rng(0))
    assert set(order[:2]) == {3, 7} and order[2] == 5
    ranks = [0] * 8
    for place, p in enumerate(order, start=4):
        ranks[p] = place
    for p, r in zip((0, 1, 2), (1, 2, 3)):
        ranks[p] = r
    ranks[4], ranks[6] = 7, 8  # busted earlier, one per round
    cfg = SimpleNamespace(players=8, payout_amounts=lambda: (50.0, 30.0, 20.0), prize_pool=100)
    busted = {1: [(6, 50)], 2: [(4, 80)], 5: [(3, 300), (5, 100), (7, 300)], 9: [(2, 900)], 12: [(1, 1200)]}
    pay = [50.0 if r == 1 else 30.0 if r == 2 else 20.0 if r == 3 else 0.0 for r in ranks]
    tally = tally_for_edge()
    _check_ranks(cfg, SimpleNamespace(ranks=tuple(ranks), prizes=tuple(pay)), busted, {0: 2400}, tally, "golden")
    assert tally.failures == []
    swapped = list(ranks)
    swapped[5], swapped[order[0]] = swapped[order[0]], swapped[5]  # the 100-chip bust placed above a 300
    tally = tally_for_edge()
    _check_ranks(cfg, SimpleNamespace(ranks=tuple(swapped), prizes=tuple(pay)), busted, {0: 2400}, tally, "golden")
    assert tally.counts["elimination"][0] == 0

