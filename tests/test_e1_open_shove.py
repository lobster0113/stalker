import numpy as np
import pytest

from referee.anchors import pushfold as P
from stalker.e1.open_shove import Game, plan_vs_raise


def _pushfold_value(stack, ante=0.0):
    push, call, _ = P.solve(stack, ante)
    pc, sb_call, _ = P._payoffs(stack, ante)
    pu, fo = P._sb_values(call, pc, sb_call, ante)
    return float((push * pu + (1 - push) * fo).sum())


def test_without_the_open_it_is_the_pushfold_game():
    g = Game(10.0)
    st = g.solve(2000, allow_open=False)
    assert g.exploitability(st, allow_open=False) < 0.01
    assert g.sb_value(st) == pytest.approx(_pushfold_value(10.0), abs=2e-3)


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
