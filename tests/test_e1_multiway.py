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
def test_trained_policy_is_constant_within_its_final_tp_buckets(view, monkeypatch):
    captured = {}
    project = M._project

    def spy(st, push_b, call_b):
        out = project(st, push_b, call_b)
        captured.update(st=out, push_b=push_b, call_b=call_b)
        return out
    monkeypatch.setattr(M, "_project", spy)
    r = M.train(SPOT, view, "beginner", "icm", 200)
    assert r.exploitability >= 0 and len(r.gains) == 3
    st = captured["st"]
    # Re-bucket against the delivered policy's own ranges: each TP value maps to one action mix.
    push_b, call_b = M._buckets(R._Tree(SPOT, R._value_fn(SPOT, "icm", 0, R.BASELINE_TOL, 200)), st, 3, view, 5)
    for p, b in push_b.items():
        for k in np.unique(b):
            assert np.ptp(st.push[p][b == k]) < 1e-6, (view, p, k)
    for key, b in call_b.items():
        for k in np.unique(b):
            assert np.ptp(st.call[key][b == k]) < 1e-6, (view, key, k)


def test_baseline_runs_the_full_iteration_count_without_early_stop():
    # #273 review: a tol-stopped baseline (10-43 iterations) made the bottleneck look free.
    tree = R._Tree(SPOT, R._value_fn(SPOT, "icm", 0, R.BASELINE_TOL, 300))
    full = R._solve_tree(tree, R._scale(SPOT, "icm"), 0.0, 300)
    assert full.iterations == 300
    r = M.train(SPOT, "rank", "beginner", "icm", 300)
    assert np.allclose(r.nash_gains, full.gains / R._scale(SPOT, "icm"))
    assert r.nash_gains.sum() < R.BASELINE_TOL  # below what a tol stop would have left
    assert r.loss == pytest.approx(r.exploitability - r.nash_gains.sum())


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
