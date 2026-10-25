import numpy as np
import pytest

from referee.sufficiency import (Cell, judge_cell, make_cell, s1_precision, s4_reproducible,
                                 s5_saturated)


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


def test_single_tournament_fails_s1():
    assert not s1_precision(_indep(500, 0.5, 1, per_t=500), rng=np.random.default_rng(0)).passed


@pytest.mark.parametrize("p,ok", [(0.65, True), (0.6501, False), (0.55, True), (0.5499, False)])
def test_s4_boundary(p, ok):
    assert s4_reproducible(_fixed(0.6), _fixed(p)) is ok


def test_s4_main_action_must_match():
    assert not s4_reproducible(_fixed(0.51), _fixed(0.49), tol=0.05)


def test_s5_boundary_and_flip():
    # tournament 0..9 mean 0.5; dropping tournaments shifts mean by a controlled amount.
    probs = [[0.5, 0.5]] * 80 + [[0.6, 0.4]] * 20
    cell = make_cell(probs, [i // 10 for i in range(100)])
    # with all 10 tournaments kept at fraction=1.0 the subset equals the cell
    assert s5_saturated(cell, fraction=1.0, rng=np.random.default_rng(0))
    # a 20% subset can differ from the full mean (0.52) by more than 2%p
    assert not all(s5_saturated(cell, fraction=0.2, tol=0.005, rng=np.random.default_rng(s)) for s in range(20))
    flip = make_cell([[0.9, 0.1]] * 10 + [[0.1, 0.9]] * 11, [i for i in range(21)])
    assert not all(s5_saturated(flip, fraction=0.3, rng=np.random.default_rng(s)) for s in range(20))


def test_same_seed_same_result_and_lessonable():
    a, b = _indep(4000, 0.7, 1), _indep(4000, 0.7, 2)
    v1, v2 = judge_cell(a, b, seed=7), judge_cell(a, b, seed=7)
    assert v1 == v2 and v1.lessonable


def test_invalid_input_has_fix_hint():
    with pytest.raises(ValueError, match="sum to 1"):
        make_cell([[0.5, 0.6]], [0])
    with pytest.raises(ValueError, match="one per decision"):
        make_cell([[0.5, 0.5]], [0, 1])
    assert isinstance(_fixed(0.5), Cell)
