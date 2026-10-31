"""Key variant b3 (#461): b1 plus the public facts (opponent seats, last bettor, preflop aggressor)."""
import json

import numpy as np
import pytest

from stalker import train_jobs as T
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR


def _play(acts, n=6, seed=3):
    s = G.deal(np.random.default_rng(seed), n)
    for a in acts:
        s = G.apply(s, a)
    return s


def _pub(s, seat, depth="full", variant="b3"):
    return K.public_key(s, seat, depth, variant)


def _field(pub, tag):
    return next(f for f in pub.split("|") if f[0] == tag and f[1:].isalnum() and f != "fcra")


FLOP_HU = ["r", "f", "f", "f", "f", "c"]    # UTG opens, the big blind calls: heads-up flop, seat 5 acts first
FLOP_LIMP = ["c", "f", "f", "f", "c", "c"]  # a limped pot: nobody raised preflop


def test_preflop_key_has_opponent_set_and_last_bettor_but_no_preflop_aggressor():
    s = _play(["r"])
    pub = _pub(s, s.to_act)
    assert _field(pub, "u") == "u02345" and _field(pub, "h") == "hb" and "|g" not in pub
    assert pub != _pub(s, s.to_act, variant="b1")


def test_opponent_seat_set_differs_only_when_a_different_opponent_is_live():
    a, b = _play(["r", "f", "c"]), _play(["r", "c", "f"])      # the same count of players, different seats
    assert a.to_act == b.to_act == 3
    assert _field(_pub(a, 3), "u") != _field(_pub(b, 3), "u")
    assert _field(_pub(a, 3), "u") == "u0245" and _field(_pub(b, 3), "u") == "u0145"


def test_last_bettor_is_none_before_me_after_me_or_me():
    assert _field(_pub(_play(["c"]), 1), "h") == "hn"
    s = _play(["r"])
    assert _field(_pub(s, 1), "h") == "hb"                     # seat 0 bet and acts before seat 1
    s = _play(FLOP_HU)
    s = G.apply(s, "b33")                                      # seat 5 bets, seat 0 acts after it postflop
    assert _field(_pub(s, 5), "h") == "hm" and _field(_pub(s, 0), "h") == "hb"
    s = _play(["r", "r"])                                      # seat 1 re-raised: seat 0 acts after it
    assert _field(_pub(s, 0), "h") == "ha"
    assert _field(_pub(s, 2), "h") == "hb"


def test_preflop_aggressor_is_none_me_a_live_opponent_or_a_folded_one():
    s = _play(FLOP_LIMP)
    assert s.street == 1 and _field(_pub(s, s.to_act), "g") == "gn"
    s = _play(FLOP_HU)
    assert s.street == 1 and s.to_act == 5
    assert _field(_pub(s, 5), "g") == "go" and _field(_pub(s, 0), "g") == "gm"
    # seat 0 opens, seat 1 3-bets, seat 0 calls: the 3-bettor is still the aggressor, and live
    s = _play(["r", "r", "c", "f", "f", "f", "c"])
    assert s.street == 1 and _field(_pub(s, 0), "g") == "go" and _field(_pub(s, 1), "g") == "gm"
    # the opener (seat 0) folds to a flop bet; on the turn the others see the raiser as folded
    s = _play(["r", "c", "f", "f", "f", "c", "b33", "f", "c"])
    assert s.street == 2 and _field(_pub(s, s.to_act), "g") == "gx"


def test_hidden_cards_do_not_change_the_public_key():
    s = _play(FLOP_HU)
    hole = list(s.hole)
    hole[0], hole[1] = hole[1], hole[0]
    assert _pub(s._replace(hole=tuple(hole)), 5) == _pub(s, 5)


def test_beginner_key_gets_only_coarse_counts_and_the_last_bettor():
    pub = _pub(_play(["r", "f", "c"]), 3, "basic")
    assert _field(pub, "u") == "u22" and _field(pub, "h") == "hb"      # seat 3: seats 0, 2 act before, 4, 5 after
    s = _play(FLOP_HU)
    basic = _pub(s, 5, "basic")
    assert "|g" not in basic and "|g" in _pub(s, 5, "full")


def test_call_or_fold_keys_stay_as_they_are():
    s = _play(["a"])
    assert "".join(G.legal(s)) in ("fc", "c")
    assert _pub(s, s.to_act) == _pub(s, s.to_act, variant="b1")


def test_b3_steps_are_b1_steps_and_the_plain_variant_is_untouched():
    s = _play(FLOP_HU)
    r = K.initial_ranges(6)
    assert np.array_equal(K.equity_steps(s, 5, r, 11, "b3", "full"), K.equity_steps(s, 5, r, 11, "b1", "full"))
    assert _pub(s, 5, variant="") == _pub(s, 5, variant="b1")
    with K.using_variant("b3"):
        assert K.public_key(s, 5) == _pub(s, 5)


def test_theoretical_keys_count_the_b3_fields():
    for depth, k in (("basic", 5), ("full", 11), ("pro", 17)):
        assert K.theoretical_keys(6, k, depth, "b3") > K.theoretical_keys(6, k, depth, "b1") > K.theoretical_keys(6, k, depth)


@pytest.mark.slow
def test_b3_training_keys_carry_the_fields_and_stay_below_the_bound():
    m = E3MCCFR(1, 5, 3, "basic", key_variant="b3")
    m.iterate(6)
    assert any("|u" in k for k in m.regret)
    assert len(m.regret) <= K.theoretical_keys(3, m.k, m.depth, "b3")


def test_b3_job_is_registered_resumable_and_matches_the_b1_job_otherwise():
    job = "e3-tp-mid-b3-w4"
    assert job in T.JOBS and job in T.RESUMABLE
    rest = lambda name: {k: v for k, v in T.JOBS[name].keywords.items() if k not in ("key_variant", "name")}  # noqa: E731
    assert T.JOBS[job].keywords["key_variant"] == "b3" and rest(job) == rest("e3-tp-mid-b1-w4")
    st = json.loads(json.dumps(E3MCCFR(1, 5, 3, "basic", key_variant="b3").state()))
    assert (st["version"], st["key_variant"]) == (4, "b3")
