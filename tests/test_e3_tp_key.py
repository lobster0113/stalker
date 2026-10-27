import numpy as np

from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def _play(s, *acts):
    for a in acts:
        s = G.apply(s, a)
    return s


def test_same_tp_situation_from_different_histories_shares_a_key():
    # The key depends on the TP situation, not on the cards dealt or the exact line: UTG opening and
    # HJ opening (BTN calls, blinds fold) give the opener the same key apart from the seat.
    a = _play(G.deal(np.random.default_rng(0)), "r", "f", "f", "c", "f", "f")
    b = _play(G.deal(np.random.default_rng(1)), "r", "f", "f", "c", "f", "f")
    assert a.history == b.history and K.public_key(a, 0) == K.public_key(b, 0)
    c = _play(G.deal(np.random.default_rng(2)), "f", "r", "f", "c", "f", "f")
    assert K.public_key(c, 1).split("|")[1:] == K.public_key(a, 0).split("|")[1:]


def test_raise_level_initiative_and_pot_odds():
    s = G.deal(np.random.default_rng(3))
    assert K.raise_level(s) == 0 and K.pot_odds_step(s, 0) == 4  # 100 to call into 150: 40%
    s = _play(s, "r")
    assert K.raise_level(s) == 1
    s = _play(s, "f", "f", "c", "f", "f")
    assert s.street == 1 and K.initiative(s, 0) == 1 and K.initiative(s, 3) == 2
    assert K.pot_odds_step(s, 0) == 0 and K.spr_step(s, 0) == 3  # 97.5BB behind into 5.75BB
    s = _play(s, "b75")
    assert K.pot_odds_step(s, 3) == 3  # 75% pot bet: 0.75 / 2.5 = 30% to call


def test_equity_steps_respect_ranges_and_scale():
    s = G.deal(np.random.default_rng(4))
    r = K.initial_ranges(6)
    st = K.equity_steps(s, 0, r, 5)
    mass = np.bincount(st[st >= 0], minlength=5) / (st >= 0).sum()
    assert np.all(np.abs(mass - 0.2) < 0.06)
    # Against five random hands, aces are near the top step and 72o at the bottom.
    from stalker.e2.eq_view import combo_index
    from stalker.core.cards import cards
    assert st[combo_index(tuple(cards("AsAd")))] == 4 and st[combo_index(tuple(cards("7h2d")))] == 0


def test_multi_equity_shrinks_with_more_opponents():
    s = G.deal(np.random.default_rng(5))
    r = K.initial_ranges(6)
    full = K.multi_equity(s, 0, r)
    s2 = _play(s, "r", "f", "f", "f", "f", "c")       # heads-up vs the BB
    hu = K.multi_equity(s2, 5, r)
    assert np.nanmean(full) < 0.25 < np.nanmean(hu)


def test_mccfr_is_reproducible_and_policies_are_distributions():
    a, b = E3MCCFR(7, 5), E3MCCFR(7, 5)
    a.iterate(2)
    b.iterate(2)
    pa = a.policy()
    assert pa == b.policy() and pa
    assert all(abs(sum(v) - 1) < 1e-9 for v in pa.values())
    assert all(k.split("|")[-1].startswith("e") for k in a.regret)
    assert len(a.regret) <= K.theoretical_keys(6, 5) * 8  # legal-set suffix aside, bounded by the TP grid
