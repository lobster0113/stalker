"""Legal actions vs the training menu (#412, TP.md section 6): every xN size is a raise-to (street total),
the menu's own rules never make a legal amount illegal, and a short all in does not reopen the betting."""
import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import translate as X


def play(s: G.State, *acts: str) -> G.State:
    for a in acts:
        assert a in G.legal(s), (a, G.legal(s), s.history)
        s = G.apply(s, a)
    return s


def to(s: G.State, a: str) -> int:
    return G._amount_to(s, a)


def real(n: int = 6, cap=None) -> G.State:
    return G.deal(np.random.default_rng(0), n, "real", cap)


def short(s: G.State, seat: int, chips: int) -> G.State:
    """Seat `seat` starts the hand with `chips` (blinds included): E3 deals equal stacks (side pots #383)."""
    stack = list(s.stack)
    stack[seat] = chips - s.bet[seat]
    return s._replace(stack=tuple(stack))


# --- to/by: every xN size is the street total after the raise ----------------------------------------

def test_preflop_open_is_raise_to_x_bb():
    assert to(real(), "r3") == 3 * G.BB                      # to 300, not 100 + 300


def test_preflop_3bet_and_4bet_are_raise_to_x_the_current_bet():
    s = play(real(), "r")                                    # open to 250
    assert to(s, "r") == 3 * 250                             # 3-bet to 750, not 250 + 3 x 250
    s = play(s, "r")
    assert to(s, "r") == 3 * 750 and to(s, "r2") == 2 * 750   # 4-bet to 2250 / 1500


def test_postflop_raise_is_raise_to_x_the_bet():
    s = play(real(2), "c", "c", "b20")                       # pot 200, bet 100 (1BB minimum)
    assert to(s, "r") == 300 and to(s, "r10") == 1000        # not 100 + 3 x 100


def test_postflop_bet_is_the_street_total_plus_a_pot_fraction():
    s = play(real(2), "r3", "c")                             # pot 600, nothing in this street yet
    assert to(s, "b50") == s.bet[s.to_act] + 300


def test_v1_menu_is_raise_to_as_well():
    s = G.deal(np.random.default_rng(0), 6)
    assert to(s, "r") == 250 and to(play(s, "r"), "r") == 750   # open 2.5BB, then 3x the open (to)


# --- menu rules are not legality rules ----------------------------------------------------------------

def test_non_all_in_5bet_is_legal_off_the_menu():
    s = play(real(3), "r", "r", "r")                         # open, 3-bet, 4-bet to 2250
    assert G.legal(s) == ["f", "c", "a"]                     # menu: a 5-bet is all in
    assert X.split(s, 5000) == [("a", 1.0)]                  # a real 5-bet to 5000 reads as the all in
    ns = G.apply_to(s, 5000, "a")
    assert ns.bet[s.to_act] == 5000 and ns.stack[s.to_act] == G.STACK - 5000


def test_min_raise_is_legal_off_the_menu():
    s = play(real(3), "r")                                   # open to 250: min raise to 400
    assert 400 not in [t for _, t in G._offered(s)]
    assert G.apply_to(s, 400, X.split(s, 400)[0][0]).bet[s.to_act] == 400
    with pytest.raises(ValueError):
        G.apply_to(s, 399, "r25")


@pytest.mark.parametrize("frac", [0.8, 0.9, 0.99])
def test_raises_to_80_99_pct_of_the_stack_are_legal(frac):
    s = play(real(2), "r", "c", "b33")                       # no cap: the menu merges these into the all in
    room = s.stack[s.to_act] + s.bet[s.to_act]
    amount = int(frac * room)
    assert all(t < G.ALLIN_MERGE * room for a, t in G._offered(s))
    ns = G.apply_to(s, amount, X.sample(s, amount, np.random.default_rng(1)))
    assert ns.bet[s.to_act] == amount and ns.stack[s.to_act] == room - amount > 0


# --- reopening -----------------------------------------------------------------------------------------

def test_short_all_in_does_not_reopen_the_betting():
    s = short(G.deal(np.random.default_rng(0), 3), 1, 450)   # BTN 0, SB 1 (450 chips), BB 2
    s = G.apply_to(s, 300, "r")                             # BTN opens to 300 (raise 200)
    s = play(s, "a")                                         # SB all in to 450: +150, short of a full raise
    assert s.last_raise == 200
    assert "a" in G.legal(s) and G.legal(s)[:2] == ["f", "c"]   # BB has not acted: it may raise
    assert G.apply_to(s, 650, "r").bet[2] == 650             # ... by at least the last full raise
    with pytest.raises(ValueError):
        G.apply_to(s, 649, "r")
    s = play(s, "c")
    assert s.to_act == 0 and G.legal(s) == ["f", "c"]         # BTN already acted: call or fold only
    with pytest.raises(ValueError):
        G.apply_to(s, 650, "r")
    with pytest.raises(ValueError):
        X.split(s, 650)
    assert play(s, "c").street == 1


def test_full_raise_all_in_reopens_and_sets_the_min_raise():
    s = short(G.deal(np.random.default_rng(0), 3), 1, 700)
    s = play(G.apply_to(s, 250, "r"), "a")                   # SB all in to 700: +450, a full raise
    assert s.last_raise == 450
    s = play(s, "c")
    assert s.to_act == 0 and "a" in G.legal(s)              # the opener may raise again
    assert G.apply_to(s, 1150, "r").bet[0] == 1150


def test_short_all_in_below_the_min_raise_is_legal_off_the_menu():
    s = short(G.deal(np.random.default_rng(0), 3), 0, 450)   # BTN has 450
    s = play(s, "r", "f")                                    # v1 open to 250, SB folds
    s = G.apply_to(s, 400, "r")                              # BB raises to 400: min re-raise 550
    ns = G.apply_to(s, 450, "a")                             # BTN all in to 450 is still a legal raise
    assert ns.stack[0] == 0 and ns.to_act == 2 and G.legal(ns) == ["f", "c"]
