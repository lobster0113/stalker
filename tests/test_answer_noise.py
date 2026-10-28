import numpy as np
import pytest

from stalker.e1 import answer_noise as N
from stalker.e1 import tp_pushfold as T


@pytest.mark.parametrize("tier", ["beginner", "mid"])
def test_edges_reproduce_the_training_buckets(tier):
    rng = np.random.default_rng(216)
    v = rng.uniform(0, 100, 400)
    w = rng.uniform(0.5, 2.0, 400)
    eq = np.searchsorted(N.edges("equity", tier), v, side="right")
    assert np.array_equal(eq, T._quantize(v, T.TIER_STEP[tier]))
    rk = np.searchsorted(N.edges("rank", tier), N.percentile(v, w), side="right")
    assert np.array_equal(rk, T._quantile_bins(v, w, T.TIER_LEVELS[tier]))


def test_bucket_probs_are_distributions():
    v = np.array([0.0, 30.0, 50.0, 99.0])
    for sigma in (0, 3, 40):
        pr = N.bucket_probs(v, N.edges("equity", "beginner"), sigma, shrink=0.2)
        assert pr.shape == (4, 5) and np.allclose(pr.sum(axis=1), 1) and (pr >= 0).all()


def test_empty_bucket_reads_the_nearest_row():
    cuts = N.edges("equity", "beginner")
    act = N.bucket_actions(np.array([0.0, 0.0, 1.0]), np.array([40.0, 45.0, 70.0]), cuts)
    assert list(act) == [0.0, 0.0, 0.0, 1.0, 1.0]


@pytest.mark.parametrize("form", list(N.FORMS))
def test_exact_learner_has_the_taught_loss_and_error_costs(form):
    r = T.train(8, 1, "beginner", 600, "random", N.FORMS[form])
    assert N.noisy_loss(r, form, 0) == pytest.approx(r.exploitability, abs=1e-9)
    assert N.noisy_loss(r, form, 20) > N.noisy_loss(r, form, 0)
