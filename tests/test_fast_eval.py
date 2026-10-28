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


def test_compiled_board_tables_equal_the_numpy_path(monkeypatch):
    from stalker.e2 import abstraction as A

    rng = np.random.default_rng(7)
    boards = [tuple(int(x) for x in rng.permutation(52)[:k]) for k in (3, 4, 5) for _ in range(4)]
    A.ehs_table.cache_clear()
    fast = [A.ehs_table(b) for b in boards]
    A.ehs_table.cache_clear()
    monkeypatch.setattr(F, "HAVE_NUMBA", False)
    slow = [A.ehs_table(b) for b in boards]
    A.ehs_table.cache_clear()
    assert all(np.array_equal(np.nan_to_num(a, nan=-1), np.nan_to_num(b, nan=-1)) for a, b in zip(fast, slow))


def _numpy_quantile_steps(xl, wl, k):
    # The numpy quantile scale the TP tiers use (#187): equal values share a step.
    vals, inv = np.unique(xl, return_inverse=True)
    mass = np.bincount(inv, wl, len(vals)) / wl.sum()
    mid = np.cumsum(mass) - mass / 2
    return np.minimum((mid * k).astype(int), k - 1)[inv]


def test_quantile_kernel_equals_the_numpy_path():
    # Runs compiled where numba is installed and as plain Python in CI: the kernel logic is checked either way.
    rng = np.random.default_rng(13)
    for _ in range(40):
        x = np.round(rng.random(1326), int(rng.integers(1, 4)))      # many ties
        w = (rng.random(1326) > 0.1) * (rng.random(1326) if rng.random() < 0.5 else 1.0)
        live = w > 0
        k = int(rng.choice([5, 11]))
        got = F.quantile_steps(x[live], w[live], k, float(w[live].sum()))
        assert np.array_equal(got, _numpy_quantile_steps(x[live], w[live], k))


def test_eval_kernel_equals_the_reference_without_numba_too():
    # #237 review: CI has no numba, so call the kernel function itself (plain Python there) on a small batch.
    rng = np.random.default_rng(237)
    hands = np.array([rng.permutation(52)[:7] for _ in range(1000)], dtype=np.int64)
    got = F._eval_many(hands, F._SH, F._POP, F._HI, F._KICK5, F._KICK3, F._KICK2, F._CAT)
    assert np.array_equal(got, reference(hands))


@pytest.mark.parametrize("board", [(0, 17, 34), (5, 22, 47, 12), (8, 9, 30, 31, 51)])
def test_board_table_kernel_path_equals_the_numpy_path(monkeypatch, board):
    # Forces the kernel path (compiled, or plain Python without numba) and compares with the numpy path.
    from stalker.e2 import abstraction as A

    monkeypatch.setattr(F, "HAVE_NUMBA", True)
    A.ehs_table.cache_clear()
    kernel = A.ehs_table(board)
    monkeypatch.setattr(F, "HAVE_NUMBA", False)
    A.ehs_table.cache_clear()
    numpy_path = A.ehs_table(board)
    A.ehs_table.cache_clear()
    assert np.array_equal(kernel, numpy_path, equal_nan=True)
