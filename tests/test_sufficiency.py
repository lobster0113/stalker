import math

import numpy as np
import pytest

from referee.sufficiency import (S1_HALF_WIDTH, judge_cell, make_cell, rule_of_three, s1_precision,
                                 s4_reproducible, s5_saturated)

# Retired metric (ADR 0008): kept for the record, run only in the full gate (#104).
pytestmark = pytest.mark.slow


def _indep(n, p, seed, per_t=1):
    rng = np.random.default_rng(seed)
    first = rng.random(n) < p
    probs = np.stack([first, ~first], axis=1).astype(float)
    return make_cell(probs, [i // per_t for i in range(n)])


def _fixed(p, n=100, n_t=10):
    return make_cell([[p, 1 - p]] * n, [i % n_t for i in range(n)])


def test_independent_large_sample_passes_s1():
    r = s1_precision(_indep(2000, 0.5, 1), rng=np.random.default_rng(0))
    assert r.passed and all(a.half_width <= 0.05 and a.ess > 385 for a in r.actions)


def test_clustered_decisions_have_small_ess_and_fail_s1():
    # 2000 decisions but only 4 tournaments, each internally constant: raw n is huge, ESS is tiny.
    p = np.repeat([[0.9, 0.1], [0.1, 0.9], [0.8, 0.2], [0.2, 0.8]], 500, axis=0)
    cell = make_cell(p, np.repeat(range(4), 500))
    r = s1_precision(cell, rng=np.random.default_rng(0))
    assert not r.passed and all(a.ess < 50 for a in r.actions)


def _deterministic(n_t, per_t=3):
    return make_cell([[0.0, 1.0]] * (n_t * per_t), [i // per_t for i in range(n_t * per_t)])


@pytest.mark.parametrize("n_t", [2, 5])
def test_small_deterministic_cell_fails_s1(n_t):
    """Zero bootstrap variance is not precision: the rule of three bounds the half-width by 3/n_tournaments."""
    r = s1_precision(_deterministic(n_t), rng=np.random.default_rng(0))
    (a,) = r.actions
    assert not r.passed and a.half_width == pytest.approx(3 / n_t) and a.ess == n_t


@pytest.mark.parametrize("n_t,ok", [(math.ceil(3 / S1_HALF_WIDTH) - 1, False), (math.ceil(3 / S1_HALF_WIDTH), True)])
def test_deterministic_cell_boundary_is_rule_of_three(n_t, ok):
    assert math.ceil(3 / S1_HALF_WIDTH) == 60
    assert s1_precision(_deterministic(n_t), rng=np.random.default_rng(0)).passed is ok


def test_near_deterministic_cell_is_also_floored():
    """One stray decision gives a tiny nonzero bootstrap width; the floor still applies (not only at zero variance)."""
    probs = [[0.0, 1.0]] * 29 + [[0.01, 0.99]]
    r = s1_precision(make_cell(probs, range(30)), rng=np.random.default_rng(0))
    (a,) = r.actions
    assert not r.passed and a.half_width == pytest.approx(rule_of_three(30))
    assert a.ess == pytest.approx(a.mean * (1 - a.mean) / (a.half_width / 1.959963984540054) ** 2)


def test_single_tournament_fails_s1():
    assert not s1_precision(_indep(500, 0.5, 1, per_t=500), rng=np.random.default_rng(0)).passed


@pytest.mark.parametrize("p,ok", [(0.65, True), (0.6501, False), (0.55, True), (0.5499, False)])
def test_s4_boundary(p, ok):
    assert s4_reproducible(_fixed(0.6), _fixed(p)) is ok


def test_s4_main_action_must_match():
    assert not s4_reproducible(_fixed(0.51), _fixed(0.49), tol=0.05)


class _FirstK:
    """Stand-in rng that keeps the first k tournaments, so S5 boundaries are deterministic."""
    sizes = []

    def choice(self, ids, size, replace):
        self.sizes.append(size)
        return ids[:size]


def _five(a, e):
    # 5 tournaments x 10 decisions; the last differs. Default 80% keeps the first 4, so diff = (a - e) / 5.
    return make_cell([[a, 1 - a]] * 40 + [[e, 1 - e]] * 10, [i // 10 for i in range(50)])


@pytest.mark.parametrize("e,ok", [(0.5, True), (0.499, False), (0.7, True), (0.701, False)])
def test_s5_boundary(e, ok):
    # 0.6 vs e: full-cell shift is (0.6 - e) / 5 = 2%p exactly at e = 0.5 and 0.7.
    assert s5_saturated(_five(0.6, e), rng=_FirstK()) is ok


def test_s5_main_action_flip_fails():
    assert not s5_saturated(_five(0.9, 0.0), rng=_FirstK())


def test_s5_two_tournaments_cannot_be_judged():
    cell = make_cell([[0.9, 0.1]] * 10 + [[0.1, 0.9]] * 12, [0] * 10 + [1] * 12)
    assert not s5_saturated(cell, rng=np.random.default_rng(0))


def test_s5_subset_never_exceeds_fraction():
    _FirstK.sizes.clear()
    cell = make_cell([[0.6, 0.4]] * 14, [i // 2 for i in range(14)])  # 7 tournaments -> 5 (71%), not 6 (86%)
    s5_saturated(cell, rng=_FirstK())
    assert _FirstK.sizes == [5]


def test_same_seed_same_result_and_lessonable():
    a, b = _indep(4000, 0.7, 1), _indep(4000, 0.7, 2)
    v1, v2 = judge_cell(a, b, seed=7), judge_cell(a, b, seed=7)
    assert v1 == v2 and v1.lessonable


def test_invalid_input_has_fix_hint():
    with pytest.raises(ValueError, match="sum to 1"):
        make_cell([[0.5, 0.6]], [0])
    with pytest.raises(ValueError, match="one per decision"):
        make_cell([[0.5, 0.5]], [0, 1])
