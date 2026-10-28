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
    assert len(a.regret) <= K.theoretical_keys(6, a.k, a.depth)  # the tier's own bound, call keys included


def test_call_or_fold_spots_share_a_short_key_across_seats():
    a = _play(G.deal(np.random.default_rng(8)), "a")                  # UTG shoves
    b = _play(G.deal(np.random.default_rng(8)), "f", "a")             # HJ shoves
    ka, kb = K.public_key(a, a.to_act), K.public_key(b, b.to_act)
    assert ka.startswith("call|0|") and ka.endswith("|fc") and ka == kb


def test_beginner_keys_drop_the_items_a_beginner_is_not_asked():
    s = _play(G.deal(np.random.default_rng(9)), "f", "r")              # HJ opens
    b = K.public_key(s, s.to_act, "basic")
    assert b.startswith("b|late|0|2|1|") and K.public_key(s, s.to_act).startswith("2|0|3|1|0|")
    # UTG and HJ are both "early": the same beginner key for the same situation.
    a = _play(G.deal(np.random.default_rng(9)), "r", "f")
    assert K.public_key(a, 2, "basic") == b
    assert K.position_group(6, 0) == K.position_group(6, 1) == "early" and K.position_group(9, 6) == "late"


def test_theoretical_bound_is_per_tier_and_holds_for_the_beginner_table():
    from stalker.e3.mccfr import E3MCCFR

    assert K.theoretical_keys(6, 5, "basic") < K.theoretical_keys(6, 5, "full")
    m = E3MCCFR(3, K.TIER_K["beginner"], 6, K.TIER_DEPTH["beginner"])
    m.iterate(40)
    assert 0 < len(m.regret) <= K.theoretical_keys(6, m.k, m.depth)


def _to_flop(seed: int = 4, n: int = 6):
    import numpy as np

    from stalker.e3 import game as G

    s = G.deal(np.random.default_rng(seed), n)
    while s.street == 0:
        s = G.apply(s, "c")
    return s


def test_range_update_narrows_the_acting_seat_only():
    # #253 review: the Bayes update `r[p] = ranges[p] * P(action | combo)`.
    import numpy as np

    from stalker.e3 import game as G
    from stalker.e3.mccfr import E3MCCFR

    s = _to_flop()
    k = 5
    m = E3MCCFR(0, k, s.n, "full")
    ranges = K.initial_ranges(s.n)
    p = s.to_act
    acts = G.legal(s)
    steps = K.equity_steps(s, p, ranges, k)
    public = K.public_key(s, p, "full")
    bet, check = acts.index("b75"), acts.index("k")
    for v in range(k):            # top step bets, everything else checks
        r = np.zeros(len(acts))
        r[bet if v >= k - 1 else check] = 1.0
        m.regret[K.key(public, v)] = r
    probs = m._seat_probs(public, steps, len(acts))
    after = K.update_range(ranges, p, probs[:, bet])
    # (a) only the actor's range changes; the others are the same objects (the equity cache relies on it)
    assert all(after[q] is ranges[q] for q in range(s.n) if q != p) and after[p] is not ranges[p]
    # (b) low steps are cut to exactly 0, top-step combos keep their weight
    assert (after[p][(steps >= 0) & (steps < k - 1)] == 0).all()
    assert np.array_equal(after[p][steps >= k - 1], ranges[p][steps >= k - 1])
    # (c) combos that collide with the board (step -1) are 0
    assert (steps == -1).any() and (after[p][steps == -1] == 0).all()
    # (d) an opponent's equity drops against the narrowed (stronger) range
    q = next(q for q in s.live() if q != p)
    before_eq = np.nanmean(K.multi_equity(s, q, ranges))
    after_eq = np.nanmean(K.multi_equity(s, q, after))
    assert after_eq < before_eq
