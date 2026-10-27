import numpy as np
import pytest

from referee.anchors.hu_equity import evaluate_batch as reference
from stalker.core import fast_eval as F
from stalker.core.cards import cards


def test_matches_the_reference_on_random_hands():
    rng = np.random.default_rng(201)
    hands = np.array([rng.permutation(52)[:7] for _ in range(30000)])
    assert np.array_equal(F.evaluate_batch(hands), reference(hands))


@pytest.mark.parametrize("hand", ["AsKsQsJsTs2d3c", "5c4c3c2cAc9d9h", "AhAdAcAs2c3d4h", "KhKdKc2s2d9c8h",
                                  "As2d3c4h5s9d9h", "7h7d7c2s3dTcJh", "8h8d4c4s2d2cJh", "9h9d3c5s7dJcKh",
                                  "2h4d6c8sTdQcAh", "AsKsQsJs9s8s2d", "6h5h4h3h2hAhKh"])
def test_matches_the_reference_on_every_category(hand):
    h = np.array([cards(hand)])
    assert F.evaluate_batch(h)[0] == reference(h)[0]


def test_falls_back_to_numpy_without_numba(monkeypatch):
    rng = np.random.default_rng(3)
    hands = np.array([rng.permutation(52)[:7] for _ in range(500)])
    monkeypatch.setattr(F, "HAVE_NUMBA", False)
    assert np.array_equal(F.evaluate_batch(hands), reference(hands))
