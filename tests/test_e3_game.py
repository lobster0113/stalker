import numpy as np
import pytest

from stalker.e3 import game as G


def _play(s, *acts):
    for a in acts:
        s = G.apply(s, a)
    return s


@pytest.mark.parametrize("n", [2, 6, 9])
def test_random_hands_finish_and_conserve_chips(n):
    rng = np.random.default_rng(n)
    for _ in range(1500 if n != 9 else 800):
        s = G.random_playout(rng, n)
        pay = G.payoff(s)
        assert pay.sum() == 0 and s.done
        assert all(0 <= x <= G.STACK for x in s.stack)
        assert max(s.total) <= G.STACK
        if len(s.live()) > 1:
            assert len(s.board) == 5
            # Equal starting stacks: everyone at showdown put in the same amount (no side pots).
            assert len({s.total[i] for i in s.live()}) == 1


def test_fold_around_gives_the_blinds_to_the_big_blind():
    s = _play(G.deal(np.random.default_rng(0)), "f", "f", "f", "f", "f")
    assert s.done and list(G.payoff(s)) == [0, 0, 0, 0, -G.SB, G.SB]


def test_preflop_order_and_big_blind_option_then_sb_first_postflop():
    s = G.deal(np.random.default_rng(1))
    assert s.to_act == 0 and G.position_names(6)[s.to_act] == "UTG"
    s = _play(s, "c", "f", "f", "c", "c")      # UTG limps, BTN and SB complete
    assert s.to_act == 5 and G.legal(s) == ["c", "r", "a"]  # BB has the option
    s = _play(s, "c")
    assert s.street == 1 and len(s.board) == 3 and s.to_act == 4  # SB first postflop
    s = _play(s, "k", "k", "k", "k")
    assert s.street == 2 and s.to_act == 4


def test_postflop_first_actor_skips_folded_blinds():
    s = _play(G.deal(np.random.default_rng(2)), "r", "f", "c", "f", "f", "f")
    assert s.street == 1 and s.to_act == 0 and set(G.legal(s)) == {"k", "b33", "b75", "a"}


def test_raise_sizes_and_cap():
    s = G.deal(np.random.default_rng(3))
    s = _play(s, "r")
    assert s.bet[0] == 250
    s = _play(s, "r")
    assert s.bet[1] == 750
    s = _play(s, "r")
    assert s.bet[2] == 1650
    assert "r" not in G.legal(s)  # three raises plus the big blind: cap reached preflop


def test_all_in_and_call_runs_the_board_out():
    s = _play(G.deal(np.random.default_rng(4)), "a", "f", "f", "f", "f", "c")
    assert s.done and len(s.board) == 5 and G.payoff(s).sum() == 0
    pay = G.payoff(s)
    assert pay[4] == -G.SB and pay[0] + pay[5] == G.SB and pay[0] in (G.STACK + G.SB, -G.STACK, G.SB // 2)


def test_illegal_action_is_rejected_with_the_legal_list():
    with pytest.raises(ValueError, match="legal"):
        G.apply(G.deal(np.random.default_rng(5)), "k")


def test_nine_handed_positions():
    assert G.position_names(9)[-3:] == ("BTN", "SB", "BB") and len(G.position_names(9)) == 9
    with pytest.raises(ValueError):
        G.deal(np.random.default_rng(0), 10)


def test_heads_up_button_is_the_small_blind_and_acts_last_postflop():
    assert G.position_names(2) == ("SB", "BB")
    s = G.deal(np.random.default_rng(6), 2)
    assert s.to_act == 0                                   # SB (button) first preflop
    s = _play(s, "c", "c")                                 # SB completes, BB checks
    assert s.street == 1 and s.to_act == 1                 # BB first postflop
    s = _play(s, "k", "k")
    assert s.street == 2 and s.to_act == 1


@pytest.mark.slow
def test_ten_thousand_random_hands_finish_and_conserve_chips():
    rng = np.random.default_rng(194)
    for n, hands in ((2, 3000), (6, 4000), (9, 3000)):
        for _ in range(hands):
            s = G.random_playout(rng, n)
            assert s.done and G.payoff(s).sum() == 0


def test_tie_split_gives_odd_chips_to_the_first_winners_in_postflop_order():
    from stalker.core.cards import cards

    s = G.deal(np.random.default_rng(0), 4)               # UTG, BTN, SB, BB
    hole = tuple(tuple(cards(h)) for h in ("2c3d", "4c5d", "6c7d", "8c9d"))
    board = tuple(cards("AsKsQsJsTs"))                    # royal flush on board: every live hand ties
    rest = tuple(c for c in range(52) if c not in board and all(c not in h for h in hole))
    s = s._replace(hole=hole, deck=board + rest)
    s = _play(s, "c", "c", "f", "c")                      # UTG, BTN call; SB folds; BB checks
    while not s.done:
        s = G.apply(s, "k")
    assert s.pot == 350 and sorted(s.live()) == [0, 1, 3]
    # 350 / 3 = 116 rest 2: postflop order is BB, UTG, BTN, so BB and UTG get the odd chips.
    assert list(G.payoff(s)) == [17, 16, -50, 17]
