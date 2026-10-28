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
    # Only consistent pairs are bottleneck policies (#268 review): 15bb pro/called cycles, 14.5bb does not.
    for stack in (3.0, 8.0, 14.5):
        r = T.train(stack, 0.0, "pro", iters=3000, sb_view="called")
        assert r.consistent, stack
        assert r.exploitability <= 0.03
        assert r.exploitability <= 3 * r.nash_exploitability + 0.002
    # The TP v0.1 definition (equity vs a random hand) leaves a measurable gap at 14.5bb.
    v01, called = (T.train(14.5, 0.0, "pro", iters=3000, sb_view=v) for v in ("random", "called"))
    assert v01.consistent and called.consistent
    assert v01.exploitability > 2 * called.exploitability


def test_delivered_pairs_are_bottleneck_policies_or_flagged():
    # #268 review: with sb_view="called" the final passes can cycle; such a pair is not a function of
    # its own TP values and must be marked, never reported as a bottleneck policy. Each case pins its
    # expected consistency so a change in either direction is reported.
    from stalker.e1 import tp_pushfold as T

    assert T.train(13.0, 0.0, "pro", iters=3000, sb_view="called").consistent is False
    cases = {(9.0, 0.0, "pro", "called"): True, (14.5, 0.0, "pro", "called"): True, (3.0, 0.0, "mid", "called"): True,
             (11.0, 0.0, "mid", "called"): False, (8.0, 1.0, "beginner", "random"): True, (13.0, 0.0, "pro", "random"): True}
    for (stack, ante, tier, view), expected in cases.items():
        r = T.train(stack, ante, tier, iters=600, sb_view=view)
        assert r.consistent is expected, (stack, ante, tier, view)
        if not r.consistent:
            continue
        step = T.TIER_STEP[tier]
        sb_b = T._quantize(T.sb_equity_when_called(r.call) if view == "called" else T.sb_equity(), step)
        bb_b = T._quantize(T.bb_equity(r.push), step)
        assert T._is_function_of(r.push, sb_b) and T._is_function_of(r.call, bb_b), (stack, ante, tier, view)
    assert all(T.train(s, 0.0, "mid", iters=300, sb_view="random").consistent for s in (3.0, 8.0, 14.0))
