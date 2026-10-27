import numpy as np
import pytest

from referee.e2 import lbr as L
from stalker.core.cards import cards
from stalker.e2 import game as G
from stalker.e2.abstraction import bucket, ehs_table
from stalker.e2.mccfr import MCCFR


def test_mccfr_is_deterministic_and_policies_are_distributions():
    a, b = MCCFR(5), MCCFR(5)
    a.iterate(60)
    b.iterate(60)
    pa, pb = a.policy(), b.policy()
    assert pa == pb and len(pa) > 50
    assert all(abs(sum(v) - 1) < 1e-9 and min(v) >= 0 for v in pa.values())


def test_buckets_order_hands_by_strength_on_a_board():
    board = tuple(cards("Kc7d2s"))
    set_k = bucket(tuple(cards("KsKd")), board)
    air = bucket(tuple(cards("4h3h")), board)
    assert set_k == 9 and air <= 3
    assert np.isnan(ehs_table(board)).sum() == 1326 - 1176  # combos using a board card


def test_equity_vs_range_matches_a_known_matchup():
    rng = np.random.default_rng(0)
    w = np.zeros(1326)
    kk = [i for i, c in enumerate(L.COMBOS) if set(c) == set(cards("KsKd"))][0]
    w[kk] = 1
    eq = np.mean([L.equity_vs_range(tuple(cards("AhAd")), (), w, rng) for _ in range(30)])
    assert eq == pytest.approx(0.82, abs=0.06)  # AA vs KK preflop ≈ 82%


def test_lbr_crushes_a_policy_that_always_folds_to_a_bet():
    def folder(key, acts):
        return [1.0 if a == "f" else 0.0 for a in acts] if "f" in acts else None
    r = L.lbr(folder, player=0, hands=40, seed=1)
    assert r.mean_bb > 0.9  # it raises every hand and collects at least the big blind


def test_lbr_is_reproducible():
    assert L.lbr({}, 1, 10, seed=4) == L.lbr({}, 1, 10, seed=4)


@pytest.mark.slow
def test_training_lowers_the_lbr_lower_bound():
    # Common random numbers: the same deals for both policies, so the comparison is not swamped by variance.
    m = MCCFR(1)
    m.iterate(3000)
    trained = L.exploitability_lb(m.policy(), 400, seed=11)["lbr_bb"]
    uniform = L.exploitability_lb({}, 400, seed=11)["lbr_bb"]
    assert trained < uniform
