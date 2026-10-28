"""E3 engine golden cases with fixed decks (#203): expected chips worked out by hand in each comment."""
import numpy as np

from stalker.core.cards import card
from stalker.e3 import game as G


def fixed(n: int, holes: list[str], board: str) -> G.State:
    """A hand with these hole cards (preflop seat order: UTG ... SB, BB) and this five-card board."""
    s = G.deal(np.random.default_rng(0), n)
    h = tuple(tuple(card(c) for c in hole.split()) for hole in holes)
    b = tuple(card(c) for c in board.split())
    used = set(sum(h, ())) | set(b)
    assert len(used) == 2 * n + 5, "cards must be distinct"
    return s._replace(hole=h, deck=b + tuple(c for c in range(52) if c not in used))


def play(s: G.State, *acts: str) -> G.State:
    for a in acts:
        assert a in G.legal(s), (a, G.legal(s), s.history)
        s = G.apply(s, a)
    return s


def test_three_way_split_gives_all_odd_chips_to_the_first_winner_in_postflop_order():
    # 6-max. UTG shoves 100BB; HJ, CO, SB, BB call; BTN folds. Pot = 5 x 10,000 = 50,000.
    # Board 2c 3d 4h 5s Kc: UTG, HJ, CO each make the wheel (A-5); SB (Q-J) and BB (K-Q, a pair) lose.
    # 50,000 / 3 = 16,666 rem 2. Postflop order is SB, BB, UTG, HJ, CO, so both odd chips go to UTG
    # (TDA odd-chip rule, as Gate R's settlement): UTG +6,668, HJ +6,666, CO +6,666, SB/BB -10,000.
    s = fixed(6, ["As 9d", "Ah 9c", "Ad 8h", "7c 7d", "Qc Jh", "Kd Qd"], "2c 3d 4h 5s Kc")
    s = play(s, "a", "c", "c", "f", "c", "c")
    assert s.done and s.street == 3
    assert list(G.payoff(s)) == [6668, 6666, 6666, 0, -10000, -10000]


def test_heads_up_order_sb_is_the_button():
    # Heads-up the SB (seat 0) is the button: first to act preflop, last after the flop.
    s = fixed(2, ["As Ks", "7d 2c"], "Qh 9h 4c 3d 2s")
    assert s.to_act == 0 and s.bet == (G.SB, G.BB)
    s = play(s, "c")             # SB completes to 1BB
    assert s.to_act == 1 and G.legal(s)[:1] == ["c"] and "f" not in G.legal(s)  # BB may check (c) for free
    s = play(s, "c")             # BB checks: flop
    assert s.street == 1 and s.to_act == 1
    s = play(s, "k")
    assert s.to_act == 0


def test_postflop_raise_cap():
    # Limped heads-up pot of 200: BB bets 33% (66, raised to the 1BB minimum = 100), SB raises to 3x =
    # 300, BB to 900 = third raise. RAISE_CAP = 3 per street, so the SB may only fold, call or shove.
    s = play(fixed(2, ["As Ks", "7d 2c"], "Qh 9h 4c 3d 2s"), "c", "c", "b33", "r", "r")
    assert s.bet == (300, 900) and G.legal(s) == ["f", "c", "a"]


def test_a_size_within_one_bb_of_all_in_is_not_offered():
    # SB with 2.5BB behind after posting (room 300): the 2.5BB open (250) would leave 50 < 1BB, so only
    # fold, call or all-in. Postflop with 150 behind and a 200 pot neither 33% (66) nor 75% (150) leaves
    # 1BB, so only check or all-in.
    s = fixed(2, ["As Ks", "7d 2c"], "Qh 9h 4c 3d 2s")
    short = s._replace(stack=(250, s.stack[1]))
    assert G.legal(short) == ["f", "c", "a"]
    flop = play(s, "c", "c")
    assert G.legal(flop._replace(stack=(flop.stack[0], 150))) == ["k", "a"]


def test_all_in_runout_deals_the_board_and_pays_the_best_hand():
    # 3-handed: UTG shoves, SB and BB call. Nobody can act, so the board runs out to the river.
    # UTG AA beats KK and QQ on 2c 7d 9h Js 3c: UTG +20,000, SB -10,000, BB -10,000.
    s = play(fixed(3, ["Ah Ad", "Kh Kd", "Qh Qd"], "2c 7d 9h Js 3c"), "a", "c", "c")
    assert s.done and s.street == 3 and len(s.board) == 5
    assert list(G.payoff(s)) == [20000, -10000, -10000]


def test_board_plays_even_split_and_uncalled_fold():
    # The board is a royal flush: a limped, checked-down heads-up pot of 200 splits 100/100 (net 0/0).
    s = play(fixed(2, ["2c 3d", "4h 5d"], "As Ks Qs Js Ts"), "c", "c", "k", "k", "k", "k", "k", "k")
    assert s.done and list(G.payoff(s)) == [0, 0]
    # SB folds preflop: BB wins the SB's 50 and keeps its own blind.
    f = play(fixed(2, ["2c 3d", "4h 5d"], "As Ks Qs Js Ts"), "f")
    assert f.done and list(G.payoff(f)) == [-50, 50]
