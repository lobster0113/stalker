"""Push/fold Nash anchor: convergence, known 10bb frequencies, EV loss."""
import numpy as np
import pytest

from referee.anchors import pushfold as pf
from stalker.core.cards import HAND_CLASSES


def test_cached_solutions_cover_grid_and_converged():
    sols = pf.table()["solutions"]
    assert len(sols) == len(pf.STACKS) * len(pf.ANTES) == 98
    worst = max(v["exploitability"] for v in sols.values())
    assert worst <= 0.01, f"exploitability {worst} bb/hand > 0.01: rerun `python -m referee.anchors.pushfold`"


@pytest.mark.parametrize("stack,ante", [(3.0, 0.0), (10.0, 0.0), (10.0, 1.0)])
def test_fresh_solve_converges_and_matches_cache(stack, ante):
    push, call, ex = pf.solve(stack, ante)
    assert ex <= 0.01
    assert pf.exploitability(stack, ante, push, call) <= 0.01
    cp, cc = pf.strategy(stack, ante)
    assert np.abs(push - cp).max() < 1e-3 and np.abs(call - cc).max() < 1e-3


def test_ten_bb_no_ante_matches_published_charts():
    # Published HU push/fold charts (e.g. HoldemResources Nash calculator, Jennings' push/fold tables):
    # at 10bb SB shoves roughly 55-60% of hands, BB calls roughly 35-40% of the shoving range.
    sb, bb = pf.frequencies(*pf.strategy(10.0))
    assert 0.55 <= sb <= 0.60, sb
    assert 0.35 <= bb <= 0.40, bb


def test_known_hands_at_10bb():
    push, call = pf.strategy(10.0)
    i = {c: k for k, c in enumerate(HAND_CLASSES)}
    assert push[i["AA"]] > 0.99 and push[i["72o"]] < 0.01 and push[i["A2o"]] > 0.99
    assert call[i["AA"]] > 0.99 and call[i["72o"]] < 0.01


def test_ranges_widen_as_stacks_shrink_and_with_ante():
    f = {s: pf.frequencies(*pf.strategy(s))[0] for s in (3, 6, 10, 15, 25)}
    assert f[3] > f[6] > f[10] > f[15] > f[25]
    assert pf.frequencies(*pf.strategy(10.0, 1.0))[0] > f[10]


def test_ev_loss_nash_is_zero_and_always_fold_is_large():
    push, _ = pf.strategy(10.0)
    pol = dict(zip(HAND_CLASSES, push))
    assert pf.ev_loss(pol.__getitem__, 10.0) <= 0.01
    assert pf.ev_loss(lambda c: 0.0, 10.0) > 0.05      # gives up the blinds' worth of value
    assert pf.ev_loss(lambda c: 1.0, 10.0) > 0.05      # shoving trash is also costly


def test_ev_loss_rejects_bad_probability():
    with pytest.raises(ValueError):
        pf.ev_loss(lambda c: 1.5, 10.0)
