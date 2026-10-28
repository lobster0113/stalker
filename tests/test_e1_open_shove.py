import numpy as np
import pytest

from referee.anchors import pushfold as P
from stalker.e1.open_shove import Game, Strategy, plan_vs_raise


def _pushfold_value(stack, ante=0.0):
    push, call, _ = P.solve(stack, ante)
    pc, sb_call, _ = P._payoffs(stack, ante)
    pu, fo = P._sb_values(call, pc, sb_call, ante)
    return float((push * pu + (1 - push) * fo).sum())


def _bb_value(g, st):
    """BB value computed from the BB's own leaf payoffs, independent of `Game.sb_value`."""
    p, a, r = g.p, g.a, g.r
    fold = 0.5 * (p * st.fold[:, None]).sum()
    shove = (p * st.shove[:, None] * (st.bbcall[None, :] * g.bb_allin - (1 - st.bbcall[None, :]) * (1 + a))).sum()
    vs3 = st.call3[:, None] * g.bb_allin + (1 - st.call3[:, None]) * r
    opn = (p * st.open[:, None] * (st.bb3[None, :] * vs3 - (1 - st.bb3[None, :]) * (1 + a))).sum()
    return float(fold + shove + opn)


def _random_strategy(rng):
    root = rng.dirichlet(np.ones(3), size=169)
    return Strategy(root[:, 0], root[:, 1], root[:, 2], *rng.random((3, 169)))


@pytest.mark.parametrize("stack,ante", [(10.0, 0.0), (10.0, 1.0), (20.0, 0.5)])
def test_payoffs_are_zero_sum(stack, ante):
    # `exploitability` adds bb_br + sb_value, which is only a BB gain if the game is zero-sum.
    g = Game(stack, ante)
    assert np.allclose(g.sb_allin + g.bb_allin, 0.0)
    rng = np.random.default_rng(174)
    for _ in range(5):
        st = _random_strategy(rng)
        assert g.sb_value(st) + _bb_value(g, st) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("stack,ante", [(10.0, 0.0), (10.0, 1.0)])
def test_without_the_open_it_is_the_pushfold_game(stack, ante):
    g = Game(stack, ante)
    st = g.solve(2000, allow_open=False)
    assert g.exploitability(st, allow_open=False) < 0.01
    assert g.sb_value(st) == pytest.approx(_pushfold_value(stack, ante), abs=2e-3)


def test_open_shove_tree_converges_and_the_open_has_value():
    g = Game(10.0)
    st = g.solve(2000)
    assert g.exploitability(st) < 0.01
    assert g.sb_value(st) > _pushfold_value(10.0)  # an extra option can only help the SB
    for arr in (st.fold + st.open + st.shove,):
        assert np.allclose(arr, 1.0)


def test_plan_vs_raise_answer_is_defined_for_openers():
    g = Game(15.0)
    st = g.solve(1500)
    plan = plan_vs_raise(g, st)
    assert plan and all(0.0 <= v <= 1.0 for v in plan.values())
    assert plan.get("AA", 1.0) == pytest.approx(1.0)  # aces never fold to the 3-bet if they open


@pytest.mark.slow
def test_open_shove_exploitability_across_stacks():
    for s in (10.0, 15.0, 20.0, 25.0):
        g = Game(s)
        assert g.exploitability(g.solve(3000)) < 0.01, s
