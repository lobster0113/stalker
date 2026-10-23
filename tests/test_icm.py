import time

import numpy as np
import pytest

from stalker.core.icm import ICMError, icm_equity, icm_equity_mc


def test_exact_sums_to_prize_pool():
    eq = icm_equity([1000, 700, 300, 50], [50, 30, 20])
    assert sum(eq) == pytest.approx(100, abs=1e-9)


def test_equal_stacks_equal_equity():
    eq = icm_equity([500] * 6, [0.5, 0.3, 0.2])
    assert eq == pytest.approx([1 / 6] * 6, abs=1e-12)


def test_winner_take_all_is_chip_proportional():
    stacks = [100, 250, 650, 1000]
    eq = icm_equity(stacks, [1.0])
    assert eq == pytest.approx([x / 2000 for x in stacks], abs=1e-12)


def test_three_player_hand_example():
    # A=50,B=30,C=20; P(A 2nd)=0.3*5/7+0.2*5/8=19/56, P(A 3rd)=9/56;
    # P(B 2nd)=0.5*0.6+0.2*3/8=0.375, P(B 3rd)=0.325.
    ea = 0.5 * 0.5 + 0.3 * 19 / 56 + 0.2 * 9 / 56
    eb = 0.5 * 0.3 + 0.3 * 0.375 + 0.2 * 0.325
    eq = icm_equity([50, 30, 20], [0.5, 0.3, 0.2])
    assert eq == pytest.approx([ea, eb, 1 - ea - eb], abs=1e-9)


def test_zero_stack_gets_nothing_and_drops_bottom_places():
    # 2 live players among 4: places 3-4 already went to the busted players.
    eq = icm_equity([0, 600, 0, 400], [50, 30, 15, 5])
    assert eq[0] == 0 and eq[2] == 0
    assert eq[1] == pytest.approx(30 + 20 * 0.6, abs=1e-9)
    assert sum(eq) == pytest.approx(80, abs=1e-9)
    mc = icm_equity_mc([0, 600, 0, 400], [50, 30, 15, 5], 1000, np.random.default_rng(0))
    assert mc[0] == 0 and mc[2] == 0 and sum(mc) == pytest.approx(80)


def test_more_payouts_than_players_ignored_beyond_field():
    assert icm_equity([10, 10], [0.6, 0.3, 0.1]) == pytest.approx([0.45, 0.45])


@pytest.mark.parametrize("stacks,payouts", [
    ([], [1.0]), ([0, 0], [1.0]), ([10, -1], [1.0]), ([10, 5], [1.0, -0.5]),
])
def test_invalid_inputs_rejected(stacks, payouts):
    with pytest.raises(ICMError):
        icm_equity(stacks, payouts)


def test_exact_limit_enforced():
    with pytest.raises(ICMError, match="icm_equity_mc"):
        icm_equity([100] * 10, [1.0])


def test_mc_matches_exact_within_half_percent():
    rng = np.random.default_rng(12345)
    for case in range(20):
        n = int(rng.integers(2, 10))
        stacks = rng.integers(1, 5000, size=n).tolist()
        k = int(rng.integers(1, n + 1))
        payouts = np.sort(rng.random(k))[::-1].tolist()
        exact = np.array(icm_equity(stacks, payouts))
        mc = np.array(icm_equity_mc(stacks, payouts, 20000, np.random.default_rng(case)))
        err = np.abs(mc - exact).max() / sum(payouts)
        assert err <= 0.005, (case, stacks, payouts, err)
        assert mc.sum() == pytest.approx(sum(payouts))


def test_mc_common_random_numbers_reproducible():
    a = icm_equity_mc([300, 200, 100], [0.7, 0.3], 500, np.random.default_rng(7))
    b = icm_equity_mc([300, 200, 100], [0.7, 0.3], 500, np.random.default_rng(7))
    assert a == b


def test_mc_performance_100_players():
    rng = np.random.default_rng(1)
    stacks = rng.integers(500, 20000, size=100)
    payouts = np.linspace(15, 1, 15)
    icm_equity_mc(stacks, payouts, 2000, rng)
    t0 = time.perf_counter()
    eq = icm_equity_mc(stacks, payouts, 2000, rng)
    assert time.perf_counter() - t0 < 0.2
    assert sum(eq) == pytest.approx(payouts.sum())
