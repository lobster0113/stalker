"""BB ante option of the E3 game (#878): dead money, settlement, c1 key slot. Gate R replays it in PokerKit."""
import numpy as np
import pytest

from stalker.e3 import game as G
from stalker.e3 import tp_key as K


def test_ante_zero_is_unchanged():
    # Recorded on main before the option existed: same seed, same hand, same result.
    s = G.random_playout(np.random.default_rng(11), 6)
    assert s.history == ("0:f", "1:f", "2:r", "3:a", "4:c", "5:f", "2:c", "/", "/", "/")
    assert [int(x) for x in G.payoff(s)] == [0, 0, 20100, -10000, -10000, -100]
    d = G.deal(np.random.default_rng(3), 6)
    assert d == G.deal(np.random.default_rng(3), 6, ante=0) and d.ante == 0


BB_TOTAL = G.BB + 100


def test_ante_is_dead_money():
    d0, d = G.deal(np.random.default_rng(5), 6), G.deal(np.random.default_rng(5), 6, ante=100)
    assert d.hole == d0.hole and d.bet == d0.bet            # same rng draws, same blinds
    assert d.total[5] == BB_TOTAL and d.stack[5] == G.STACK - BB_TOTAL and d.pot == d0.pot + 100
    assert d.to_call(0) == G.BB                              # the ante is not part of the price
    assert G.legal(d) == G.legal(d0)


def test_everyone_folds_big_blind_takes_blind_and_ante():
    s = G.deal(np.random.default_rng(1), 6, ante=100)
    for _ in range(5):
        s = G.apply(s, "f")
    assert s.done and list(G.payoff(s)) == [0, 0, 0, 0, -50, 50]    # SB loses 50, BB nets the SB; its ante comes back


def test_short_big_blind_pays_ante_first():
    s = G.deal(np.random.default_rng(1), 3, stacks=(10000, 10000, 150), ante=100)
    assert (s.ante, s.bet[2], s.stack[2]) == (100, 50, 0)
    s = G.deal(np.random.default_rng(1), 3, stacks=(10000, 10000, 80), ante=100)
    assert (s.ante, s.bet[2], s.stack[2], s.to_call(0)) == (80, 0, 0, 50)


def test_ante_only_big_blind_wins_main_pot_only():
    # BB all in for its 80-chip ante: it can win the ante layer, not the 50s the others put in beyond it.
    for seed in range(40):
        s = G.deal(np.random.default_rng(seed), 3, stacks=(10000, 10000, 80), ante=100)
        while not s.done:
            s = G.apply(s, "c" if "c" in G.legal(s) else "k")
        pay = G.payoff(s)
        assert int(pay.sum()) == 0 and -80 <= pay[2] <= 0   # it can only win its own 80


@pytest.mark.parametrize("stacks", [None, (10000, 3000, 10000, 10000), (10000, 10000, 10000, 900)])
def test_chips_conserved_in_every_hand(stacks):
    rng = np.random.default_rng(7)
    for _ in range(150):
        s = G.random_playout(rng, 4, stacks=stacks, ante=100)
        assert int(G.payoff(s).sum()) == 0 and s.pot == sum(s.total)


def test_c1_key_ante_slot_follows_the_deal():
    with K.using_variant("c1"):
        a = K.public_key(G.deal(np.random.default_rng(2), 6), 0)
        b = K.public_key(G.deal(np.random.default_rng(2), 6, ante=100), 0)
    assert "|tc0|" in a and "|tc1|" in b       # (pot odds differ too: the ante is in the pot)


def test_negative_ante_rejected():
    with pytest.raises(ValueError):
        G.deal(np.random.default_rng(0), 6, ante=-1)
