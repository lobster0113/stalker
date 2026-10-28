"""#261: the noisy TP learner and its decision-loss simulation."""
import numpy as np
import pytest

from stalker.e2 import game as G
from stalker.e2.abstraction import TIERS
from stalker.e2.eq_view import combo_index, eq_buckets, equity_vs
from stalker.tp import noise_sim as S
from stalker.tp.noise_learner import (LEVELS, Level, chip_equity_form, chip_pct_form, perceive,
                                      rank_positions, step_of_value)

K = 5


def _spots():
    rng = np.random.default_rng(3)
    for _ in range(4):
        s = G.deal(rng)
        for n in (0, 3, 5):
            yield s, tuple(s.deck[:n])


def test_exact_learner_gives_the_true_chip():
    exact = LEVELS["exact"]
    rng = np.random.default_rng(0)
    ones = np.ones(len(S.COMBOS))
    for s, board in _spots():
        hole = combo_index(s.hole[0])
        assert chip_equity_form(equity_vs(board, ones), hole, K, exact, rng) == eq_buckets(board, ones, K)[hole]
        assert chip_pct_form(S.pct_stat(board), hole, K, exact, rng) == TIERS["beginner"].combo_buckets(board)[hole]


def test_same_seed_same_answers_other_seed_differs():
    s, board = next(iter(_spots()))
    stat = S.pct_stat(board)
    hole = combo_index(s.hole[0])
    run = lambda seed: [chip_pct_form(stat, hole, K, LEVELS["beginner"], r) for r in [np.random.default_rng(seed)] * 40]
    assert run(1) == run(1)
    assert run(1) != run(2)


def test_anchor_one_answers_the_middle_whatever_the_truth():
    rng = np.random.default_rng(0)
    lv = Level(sigma=0.0, anchor=1.0)
    assert all(perceive(x, lv, rng) == 0.5 for x in (0.0, 0.3, 1.0))
    stat = np.linspace(0, 1, 101)
    assert {chip_equity_form(stat, h, K, lv, rng) for h in (0, 50, 100)} == {2}


def test_noise_widens_chip_errors_with_sigma():
    stat = np.linspace(0, 1, 1001)
    rng = np.random.default_rng(0)
    err = {}
    for name in ("expert", "beginner"):
        true = chip_equity_form(stat, 600, K, LEVELS["exact"], rng)
        err[name] = np.mean([abs(chip_equity_form(stat, 600, K, LEVELS[name], rng) - true) for _ in range(400)])
    assert err["beginner"] > err["expert"]


def test_rank_positions_ties_share_and_cover_unit_interval():
    stat = np.array([1.0, 1.0, 2.0, np.nan, 3.0])
    pos = rank_positions(stat, ~np.isnan(stat))
    assert pos[0] == pos[1] and np.isnan(pos[3]) and 0 < np.nanmin(pos) < np.nanmax(pos) < 1
    assert step_of_value(2.0, np.sort(stat[~np.isnan(stat)]), 4) == 2


@pytest.mark.parametrize("form", S.FORMS)
def test_loss_is_zero_for_exact_and_reproducible(form):
    policy = S.train(form, 40, 1)
    assert S.loss(form, policy, "exact", 30, 5)["loss_bb"] == 0.0
    a, b = S.loss(form, policy, "beginner", 30, 5), S.loss(form, policy, "beginner", 30, 5)
    assert a == b and a["ci95_bb"] >= 0
