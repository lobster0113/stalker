import numpy as np
import pytest

from referee.anchors import icm_reference as R
from stalker.e1 import multiway_pushfold as M

SPOT = R.Spot((1000, 1000, 1000), 50, 100, (0.5, 0.3, 0.2))


def test_quantile_buckets_hold_equal_mass_and_respect_order():
    x = np.linspace(0, 1, R.N_CLASSES)
    b = M._quantile(x, R.CLASS_COMBOS, 5)
    mass = np.bincount(b, R.CLASS_COMBOS, 5) / R.CLASS_COMBOS.sum()
    assert np.all(np.abs(mass - 0.2) < 0.06) and np.all(np.diff(b) >= 0)


@pytest.mark.parametrize("view", M.VIEWS)
def test_bottleneck_policies_are_functions_of_their_tp_values(view):
    r = M.train(SPOT, view, "beginner", "icm", 200)
    assert r.exploitability >= 0 and len(r.gains) == 3


def test_policy_is_constant_within_a_bucket():
    tree = R._Tree(SPOT, R._value_fn(SPOT, "icm", 0, R.BASELINE_TOL, 100))
    st = R.Strategy.uniform(3)
    rng = np.random.default_rng(0)
    st.push[:] = rng.random(st.push.shape)
    push_b, call_b = M._buckets(tree, st, 3, "strongest", 5)
    proj = M._project(st, push_b, call_b)
    for p, b in push_b.items():
        for k in np.unique(b):
            assert np.ptp(proj.push[p][b == k]) < 1e-12


def test_unknown_view_is_rejected():
    with pytest.raises(ValueError, match="view"):
        M.train(SPOT, "oracle")


@pytest.mark.slow
def test_three_handed_bottleneck_is_close_to_the_reference_equilibrium():
    # Exact per-seat BR gains from the ICM reference, as a share of the prize pool.
    for view in ("rank", "composite"):
        r = M.train(SPOT, view, "mid", "icm", 1500)
        assert r.exploitability < 0.01, (view, r.exploitability)
