import numpy as np
import pytest

from stalker.core.cards import cards
from stalker.core.evaluator import evaluate
from stalker.e2 import game as G


def _play(seq, hole="AhAdKsKd", deck=None):
    c = cards(hole)
    rest = [x for x in range(52) if x not in c] if deck is None else deck
    s = G.State(hole=((c[0], c[1]), (c[2], c[3])), deck=tuple(rest))
    for a in seq:
        s = G.apply(s, a)
    return s


def test_preflop_raise_ladder_and_cap():
    s = _play(["r"])
    assert s.bet == (250, 100)                     # open to 2.5BB
    s = G.apply(s, "r")
    assert s.bet == (250, 750)                     # 3-bet to 3x
    s = G.apply(s, "r")
    assert s.bet == (1650, 750)                    # 4-bet to 2.2x
    assert G.legal(s) == ["f", "c", "a"]           # raise cap reached: only fold, call, all in


def test_limp_gives_the_big_blind_an_option_then_flop():
    s = _play(["c"])
    assert not s.done and s.to_act == 1 and "f" not in G.legal(s)
    s = G.apply(s, "c")                            # BB checks its option
    assert s.street == 1 and len(s.board) == 3 and s.to_act == 1 and G.legal(s)[:1] == ["k"]


def test_postflop_bet_sizes_follow_the_pot():
    s = _play(["c", "c"])                          # pot 200
    s = G.apply(s, "b75")
    assert s.bet == (0, 150)
    s2 = G.apply(_play(["c", "c"]), "b33")
    assert s2.bet == (0, 100)                      # 66 rounds up to the 1BB minimum


def test_all_in_runs_the_board_out_and_pays_by_the_evaluator():
    s = _play(["a", "c"])
    assert s.done and len(s.board) == 5 and s.stack == (0, 0)
    v0, v1 = evaluate(list(s.hole[0]) + list(s.board)), evaluate(list(s.hole[1]) + list(s.board))
    assert G.payoff(s) == (G.STACK if v0 > v1 else -G.STACK if v0 < v1 else 0)
    assert G.legal(s) == []


def test_fold_pays_what_was_put_in():
    assert G.payoff(_play(["f"])) == -G.SB
    assert G.payoff(_play(["r", "f"])) == G.BB


def test_illegal_actions_are_rejected():
    with pytest.raises(ValueError, match="illegal action 'k'"):
        _play(["k"])
    with pytest.raises(ValueError, match="illegal"):
        G.apply(_play(["a", "c"]), "c")


def test_random_play_conserves_chips_and_matches_the_evaluator():
    rng = np.random.default_rng(7)
    for _ in range(10_000):
        s = G.deal(rng)
        inc = {}  # largest raise increment so far on each street (the big blind preflop)
        while not s.done:
            acts = G.legal(s)
            if 0 in s.stack:
                # Someone is all in: the only decision left is answering it, never putting in more.
                assert s.to_call() > 0 and set(acts) <= {"f", "c"}, (s.history, acts)
            a = rng.choice(acts)
            ns = G.apply(s, a)
            if a in ("r", "b33", "b75") or (a == "a" and ns.street == s.street and ns.bet[s.to_act] > max(s.bet)):
                step = ns.bet[s.to_act] - max(s.bet)
                floor = max(G.BB, inc.get(s.street, G.BB if s.street == 0 else 0))
                if a != "a":
                    assert step >= floor, (s.history, a, step, floor)  # min-raise rule; only all-in may be short
                if step >= floor:
                    inc[s.street] = step
            s = ns
        assert sum(s.stack) + s.pot == 2 * G.STACK
        v = G.payoff(s)
        if s.folded is None:
            assert len(s.board) == 5
            v0, v1 = evaluate(list(s.hole[0]) + list(s.board)), evaluate(list(s.hole[1]) + list(s.board))
            assert (v > 0) == (v0 > v1) and (v < 0) == (v0 < v1)
        assert abs(v) <= G.STACK


def test_deal_is_seeded():
    assert G.deal(np.random.default_rng(3)) == G.deal(np.random.default_rng(3))


def test_public_tree_is_small_and_finite():
    # Exact sizes, reported in ADR 0012 and docs/ARCHITECTURE.md; a menu change must update them.
    assert G.public_tree_size() == {"preflop": 16, "flop": 116, "turn": 628, "river": 2548}
