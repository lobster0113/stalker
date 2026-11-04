import math

import numpy as np
import pytest

from stalker.toy import aivat as a

N = 3000


def test_rules_three_way_check_and_bet_fold_call():
    assert a.to_act("") == 0 and a.to_act("ppp") is None
    assert a.to_act("pb") == 2 and a.to_act("pbp") == 0 and a.to_act("pbpb") is None
    # Seat 1 bets, seat 2 folds, seat 0 calls: showdown between 0 and 1, pot 5.
    assert a.payoff((3, 2, 1), "pbpb").tolist() == [3, -2, -1]
    assert a.payoff((0, 1, 2), "ppp").tolist() == [-1, -1, 2]
    for d in a.DEALS[:5]:
        assert a.payoff(d, "bbb").sum() == 0


@pytest.mark.parametrize("name,v,known", [
    ("exact-all", a.exact_value(a.default_strategy), frozenset({0, 1, 2})),
    ("exact-opp", a.exact_value(a.default_strategy), frozenset({1, 2})),
    ("showdown-all", a.showdown_value(), frozenset({0, 1, 2})),
    ("negated", a.negated(a.showdown_value()), frozenset({0, 1, 2})),
])
def test_aivat_mean_matches_raw_mean_within_two_se(name, v, known):
    raw, est = a.simulate(N, np.random.default_rng(11), v=v, known=known)
    assert abs(est.mean() - raw.mean()) <= 2 * a.se(raw), name
    assert abs(est.mean() - a.true_value()) <= 2 * max(a.se(est), 1e-12), name


def test_good_value_function_reduces_variance_and_a_bad_one_can_increase_it():
    rng = lambda: np.random.default_rng(5)
    raw, good = a.simulate(N, rng(), v=a.showdown_value(), known=frozenset({1, 2}))
    _, bad = a.simulate(N, rng(), v=a.negated(a.showdown_value()))
    assert a.se(good) / a.se(raw) < 1
    assert a.se(bad) / a.se(raw) > 1


def test_exact_value_with_all_seats_known_is_the_constant_true_value():
    _, est = a.simulate(200, np.random.default_rng(0))
    assert np.allclose(est, a.true_value(), atol=1e-12)


def test_seeded_generator_reproduces_and_seeds_differ():
    x = a.simulate(300, np.random.default_rng(3), v=a.showdown_value())
    y = a.simulate(300, np.random.default_rng(3), v=a.showdown_value())
    z = a.simulate(300, np.random.default_rng(4), v=a.showdown_value())
    assert all(np.array_equal(p, q) for p, q in zip(x, y))
    assert not np.array_equal(x[0], z[0])


def test_table_rows_report_finite_ratio_unless_exact():
    rows = a.table(n=500, seed=1)
    assert rows[0]["se_ratio"] == math.inf
    assert all(math.isfinite(r["se_ratio"]) for r in rows[1:])
