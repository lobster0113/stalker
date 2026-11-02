"""#448: the avg_cap option of the toy E3 sampler and the variance study on three-handed Kuhn."""
import numpy as np
import pytest

from stalker.vcfr import avg_variance as V
from stalker.vcfr import toy as T


def _sample(cap, seed=3):
    root = T.kuhn3()
    rng = np.random.default_rng(0)
    sigma = {k: rng.dirichlet(np.full(a, 0.3)) for k, (_, a) in sorted(T.keys(root).items())}
    return T.E3Sampler(root, avg_rule="own", avg_cap=cap).sample(sigma, 0, np.random.default_rng(seed))[1]


def test_no_cap_and_huge_cap_are_bit_identical():
    a, b = _sample(None), _sample(1e18)
    assert a.keys() == b.keys() and all(np.array_equal(a[k], b[k]) for k in a)


def test_cap_only_shrinks_the_weights():
    a, b = _sample(None), _sample(1.0)
    assert all((b[k] <= a[k] + 1e-12).all() for k in a) and any((b[k] < a[k] - 1e-9).any() for k in a)


def test_study_is_unbiased_in_shape_and_exact_pass_runs():
    rows = {r["estimator"]: r for r in V.study(steps=20, reps=3)}
    assert set(rows) == set(V.ESTIMATORS)
    assert all(0 <= r["bias_l1"] <= r["mean_err_l1"] + 1e-9 for r in rows.values())


def test_study_is_reproducible():
    assert V.study(steps=20, reps=2, seed=5) == V.study(steps=20, reps=2, seed=5)
