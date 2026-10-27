import numpy as np
import pytest

from referee.anchors import pushfold as P
from stalker.e1 import tp_pushfold as T


def test_equity_views_are_consistent():
    # Against a range of every hand, BB equity is the same "vs random" equity the SB sees.
    assert T.bb_equity(np.ones(169)) == pytest.approx(T.sb_equity(), abs=1e-9)
    assert T.sb_equity_when_called(np.ones(169)) == pytest.approx(T.sb_equity(), abs=1e-9)
    aa = 0
    assert T.sb_equity()[aa] > 84


def test_seat_gains_sum_to_exploitability():
    rng = np.random.default_rng(0)
    push, call = rng.random(169), rng.random(169)
    sb, bb = T.seat_gains(8.0, 0.0, push, call)
    assert sb >= 0 and bb >= 0
    assert sb + bb == pytest.approx(P.exploitability(8.0, 0.0, push, call), abs=1e-12)


@pytest.mark.parametrize("view", ["random", "called"])
def test_trained_policies_are_functions_of_the_tp_value(view):
    r = T.train(8.0, 0.0, "mid", iters=500, sb_view=view)
    sb_b = T._quantize(T.sb_equity() if view == "random" else T.sb_equity_when_called(r.call), 10)
    bb_b = T._quantize(T.bb_equity(r.push), 10)
    for buckets, pol in ((sb_b, r.push), (bb_b, r.call)):
        for b in np.unique(buckets):
            assert np.ptp(pol[buckets == b]) < 1e-12, "classes with the same TP value must act the same"


def test_finer_tp_scale_costs_less():
    beginner = T.train(10.0, 0.0, "beginner", iters=800, sb_view="called").exploitability
    pro = T.train(10.0, 0.0, "pro", iters=800, sb_view="called").exploitability
    assert pro < beginner


@pytest.mark.slow
def test_e1_pro_tier_with_equity_when_called_is_near_nash():
    # Exact Gate Q4 numbers on a stack spread; the draft target (plan §4.6) is pro <= 0.03 bb/hand.
    for stack in (3.0, 8.0, 15.0):
        r = T.train(stack, 0.0, "pro", iters=3000, sb_view="called")
        assert r.exploitability <= 0.03
        assert r.exploitability <= 3 * r.nash_exploitability + 0.002
    # The TP v0.1 definition (equity vs a random hand) leaves a measurable gap at 15bb.
    v01 = T.train(15.0, 0.0, "pro", iters=3000, sb_view="random").exploitability
    assert v01 > 2 * T.train(15.0, 0.0, "pro", iters=3000, sb_view="called").exploitability


def test_quantile_bins_hold_equal_mass():
    _, p = __import__("referee.anchors.pushfold", fromlist=["_tables"])._tables()
    w = p.sum(axis=1)
    b = T._quantile_bins(T.sb_equity(), w, 5)
    mass = np.bincount(b, w, 5) / w.sum()
    assert set(b) == set(range(5)) and np.all(np.abs(mass - 0.2) < 0.05), mass
    # Monotone: a better hand never lands in a lower bucket.
    order = np.argsort(T.sb_equity())
    assert np.all(np.diff(b[order]) >= 0)


def test_unknown_scale_is_rejected():
    with pytest.raises(ValueError, match="scale"):
        T.train(8.0, 0.0, "beginner", iters=10, scale="log")


@pytest.mark.slow
def test_quantile_beginner_scale_beats_uniform_and_meets_target():
    # Draft E1 target for beginners (plan §4.6): <= 0.10 bb/hand.
    for stack in (10.0, 15.0):
        uni = T.train(stack, 0.0, "beginner", iters=2000, sb_view="called", scale="uniform").exploitability
        qua = T.train(stack, 0.0, "beginner", iters=2000, sb_view="called", scale="quantile").exploitability
        assert qua < uni and qua <= 0.10, (stack, uni, qua)
