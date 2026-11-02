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


def _setup():
    root = T.kuhn3()
    sigmas = V.trajectory(root, np.random.default_rng(2), 5, 0.3)
    return root, sigmas


def test_expected_increment_without_cap_is_the_exact_own_update():
    root, (sigma, *_) = _setup()
    for p in range(3):
        got, want = V.expected_increment(root, sigma, p, None), T.exact_update(root, T.identity, sigma, p, 3, "own")[1]
        assert got.keys() == want.keys() and all(np.allclose(got[k], want[k], atol=1e-12) for k in want)


def test_expected_increment_matches_the_sampler_mean_with_cap():
    root, (sigma, *_) = _setup()
    s, rng, n = T.E3Sampler(root, avg_rule="own", avg_cap=2.0), np.random.default_rng(1), 4000
    tot: T.Table = {}
    for _ in range(n):
        for k, v in s.sample(sigma, 1, rng)[1].items():
            T._acc(tot, k, v / n)
    want = V.expected_increment(root, sigma, 1, 2.0)
    assert max(float(np.abs(tot[k] - want[k]).max()) for k in want) < 0.1 * max(float(v.max()) for v in want.values())


def test_study_rows_uncapped_is_unbiased_and_exact_pass_has_err_equal_bias():
    rows = {r["estimator"]: r for r in V.study(steps=20, reps=3)}
    assert set(rows) == set(V.ESTIMATORS)
    assert rows["exact"]["bias_l1"] == rows["exact"]["mean_err_l1"]
    root, sigmas = _setup()
    assert max(float(np.abs(V.expected_policy(root, sigmas, None)[k]
                            - V.expected_policy(root, sigmas, 1e18)[k]).max()) for k in T.keys(root)) < 1e-12


def test_study_is_reproducible():
    assert V.study(steps=20, reps=2, seed=5) == V.study(steps=20, reps=2, seed=5)
