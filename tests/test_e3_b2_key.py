"""Key variant b2 (#460): board.adv / opp.value / plan.foldeq on top of b1 in the TP key."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from stalker import train_jobs as T
from stalker.core.cards import cards, combo_index
from stalker.e3 import game as G
from stalker.e3 import tp_key as K
from stalker.e3.mccfr import E3MCCFR, coverage

HU = (0, 5)
_REAL_LEGAL = G.legal


@pytest.fixture(autouse=True)
def _mock_legal(monkeypatch):
    """The hand-built states below have no betting state: a bet is legal unless a test says otherwise."""
    monkeypatch.setattr(G, "legal", lambda st: _REAL_LEGAL(st) if isinstance(st, G.State) else ["k", "b33", "a"])


def _state(board_text, history=(), live=HU):
    b = cards(board_text)
    return SimpleNamespace(street=len(b) - 2, board=b, live=lambda: list(live), history=tuple(history),
                           pot=100, done=False, to_call=lambda seat: 0)


def _ranges(**tops):
    r = K.initial_ranges(6)
    for seat, mask in tops.items():
        r[int(seat[1:])] = mask
    return r


def _strong(board_text, share):
    """A range with only the strongest `share` of combos on this board."""
    strength = K._equity_cached(tuple(cards(board_text)), K._UNIFORM)
    ok = ~np.isnan(strength)
    return np.where(ok & (strength >= np.nanquantile(strength, 1 - share)), 1.0, 0.0)


def test_board_adv_differs_for_ranges_that_hit_the_board_differently_at_the_same_b1_fields():
    s = _state("Ks7s2d")
    even = K.board_adv(s, 0, K.initial_ranges(6))
    mine_strong = K.board_adv(s, 0, _ranges(r0=_strong("Ks7s2d", 0.2)))
    opp_strong = K.board_adv(s, 0, _ranges(r5=_strong("Ks7s2d", 0.2)))
    assert mine_strong < 40 < even < 60 < opp_strong
    codes = [int(K.b2_code(s, 0, r, "full")[0]) for r in (K.initial_ranges(6), _ranges(r0=_strong("Ks7s2d", 0.2)),
                                                           _ranges(r5=_strong("Ks7s2d", 0.2)))]
    assert len(set(c % K.B1_RADIX for c in codes)) == 3        # three adv buckets, nothing else compared
    base = K.equity_steps(s, 0, K.initial_ranges(6), 11, "b1", "full")
    a = K.equity_steps(s, 0, _ranges(r5=_strong("Ks7s2d", 0.2)), 11, "b2", "full")
    assert (a[a >= 0] // K.B2_BASE >= 1).all() and a.shape == base.shape


def test_board_adv_is_not_asked_multiway_or_preflop():
    assert K.board_adv(_state("Ks7s2d", live=(0, 3, 5)), 0, K.initial_ranges(6)) is None
    assert K.b2_label(int(K.b2_code(_state("Ks7s2d", live=(0, 3, 5)), 0, K.initial_ranges(6), "full")[0])).startswith("a-")


def test_opp_value_is_na_without_an_opponent_bet_and_set_with_one():
    r = K.initial_ranges(6)
    quiet = _state("Ks7s2d", history=("5:k",))
    assert K.opp_value(quiet, 0, r) is None and K.opp_value(_state("Ks7s2d", history=("0:b33",)), 0, r) is None
    bet = _state("Ks7s2d", history=("5:b75",))
    assert 0 <= K.opp_value(bet, 0, r) <= 100
    street_back = _state("Ks7s2d9c", history=("5:b75", "0:c", "/", "5:k"))     # the bet was on the flop
    assert K.opp_value(street_back, 0, r) is None
    assert "w-" in K.b2_label(int(K.b2_code(quiet, 0, r, "full")[0]))


def test_opp_value_is_higher_when_the_bettor_holds_a_value_range():
    s = _state("Ks7s2d", history=("5:b75",))
    strong, weak = _ranges(r5=_strong("Ks7s2d", 0.1)), _ranges(r5=1.0 - _strong("Ks7s2d", 0.6))
    assert K.opp_value(s, 0, strong) > 65 > 35 > K.opp_value(s, 0, weak)


def test_plan_foldeq_is_na_when_no_bet_or_raise_is_legal(monkeypatch):
    s = _state("Ks7s2d")
    monkeypatch.setattr(G, "legal", lambda st: ["f", "c"])
    assert K.plan_foldeq(s, 0, K.initial_ranges(6)) is None
    assert "f-" in K.b2_label(int(K.b2_code(s, 0, K.initial_ranges(6), "full")[0]))
    monkeypatch.setattr(G, "legal", lambda st: ["k", "b33", "a"])
    assert 0 < K.plan_foldeq(s, 0, K.initial_ranges(6)) < 1


def test_plan_foldeq_rises_when_the_opponents_range_is_weak_and_multiway_is_the_product(monkeypatch):
    monkeypatch.setattr(G, "legal", lambda st: ["k", "b33", "a"])
    s = _state("Ks7s2d")
    mine = _strong("Ks7s2d", 0.1)
    weak, strong = 1.0 - _strong("Ks7s2d", 0.7), _strong("Ks7s2d", 0.4)
    f_weak = K.plan_foldeq(s, 0, _ranges(r0=mine, r5=weak))
    f_strong = K.plan_foldeq(s, 0, _ranges(r0=mine, r5=strong))
    assert f_weak > f_strong
    multi = _state("Ks7s2d", live=(0, 3, 5))
    both = K.plan_foldeq(multi, 0, _ranges(r0=mine, r3=weak, r5=weak))
    assert both == pytest.approx(f_weak ** 2)


def test_grade_depth_beginner_asks_adv_only_and_the_others_ask_all_three():
    s = _state("Ks7s2d", history=("5:b75",))
    basic = K.b2_label(int(K.b2_code(s, 0, K.initial_ranges(6), "basic")[0]))
    assert basic[0] == "a" and "w" not in basic and "f" not in basic
    for depth in ("full", "pro"):
        assert set(K.b2_label(int(K.b2_code(s, 0, K.initial_ranges(6), depth)[0]))) >= set("awf")


def _flop(seed):
    s = G.deal(np.random.default_rng(seed))
    while s.street == 0:
        s = G.apply(s, "c" if "c" in G.legal(s) else "k")
    return s


def test_hidden_cards_do_not_change_the_b2_part():
    a = _flop(3)
    b = a._replace(hole=tuple(reversed(a.hole)))               # other hole cards, same public state
    r = K.initial_ranges(a.n)
    ca, cb = (K.b2_code(s, s.to_act, r, "full") for s in (a, b))
    assert np.array_equal(ca, cb) and (ca == ca[0]).all()      # one value for all combos: nothing about my cards
    sa, sb = (K.equity_steps(s, s.to_act, r, 11, "b2", "full") // K.B2_BASE for s in (a, b))
    assert np.array_equal(sa, sb)


def test_key_string_carries_both_labels_and_call_and_preflop_keys_do_not():
    b1, b2 = 7, 9
    step = 3 + K.B1_BASE * (1 + b1) + K.B2_BASE * (1 + b2)
    assert K.key("pub", step) == f"pub|e3|{K.b1_label(b1)}|{K.b2_label(b2)}"
    assert K.key("call|1|1|2", step) == "call|1|1|2|e3"
    assert K.key("pub", 3 + K.B1_BASE * (1 + b1)) == f"pub|e3|{K.b1_label(b1)}"
    pre = G.deal(np.random.default_rng(0))
    plain = K.equity_steps(pre, pre.to_act, K.initial_ranges(6), 11)
    assert np.array_equal(plain, K.equity_steps(pre, pre.to_act, K.initial_ranges(6), 11, "b2", "full"))


def test_b2_steps_extend_b1_steps_without_touching_the_b1_part():
    s = _state("Ks7s9s")
    r = K.initial_ranges(6)
    b1 = K.equity_steps(s, 0, r, 11, "b1", "full")
    b2 = K.equity_steps(s, 0, r, 11, "b2", "full")
    ok = b1 >= 0
    assert ((b2[ok] % K.B2_BASE) == b1[ok]).all() and (b2[~ok] == b1[~ok]).all()


def test_theoretical_keys_count_the_b2_fields():
    for n, k, depth in ((6, 11, "full"), (6, 5, "basic"), (6, 17, "pro")):
        b1, b2, plain = (K.theoretical_keys(n, k, depth, v) for v in ("b1", "b2", ""))
        assert b2 > b1 > plain
    full = K.theoretical_keys(6, 11, "full", "b2") // K.theoretical_keys(6, 11, "full", "b1")
    basic = K.theoretical_keys(6, 5, "basic", "b2") / K.theoretical_keys(6, 5, "basic", "b1")
    assert 3 <= basic <= 4 and 40 <= full <= 64   # (3+N/A)^3 = 64 resp. 4 postflop, diluted by preflop and call keys


def test_b2_trains_checkpoints_and_resumes_as_b2():
    m = E3MCCFR(1, 5, 3, "basic", key_variant="b2")
    m.iterate(3)
    st = json.loads(json.dumps(m.state()))
    assert st["key_variant"] == "b2" and E3MCCFR.from_state(st).key_variant == "b2"
    assert set(coverage(m)) <= set(K.LEGAL_PREFLOP) | set(K.LEGAL_POSTFLOP) | set(K.LEGAL_CALL)
    assert any("|a" in k for k in m.visits)


def test_b2_job_is_registered_resumable_and_matches_the_b1_job():
    job = T.JOBS["e3-tp-mid-b2-w4"]
    ref = T.JOBS["e3-tp-mid-b1-w4"]
    assert job.keywords["key_variant"] == "b2" and "e3-tp-mid-b2-w4" in T.RESUMABLE
    assert {k: v for k, v in job.keywords.items() if k not in ("name", "key_variant")} == \
           {k: v for k, v in ref.keywords.items() if k not in ("name", "key_variant")}
