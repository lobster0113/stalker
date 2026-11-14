import math

import numpy as np
import pytest

from stalker.core.icm import bubble_corrected_equity, icm_equity

PAYOUTS = [50.0, 30.0, 20.0]


def _random_stacks(rng, n):
    return rng.integers(1, 10_000, size=n).tolist()


def test_lambda_zero_equals_icm():
    rng = np.random.default_rng(865)
    for _ in range(20):
        n = int(rng.integers(2, 8))
        stacks = _random_stacks(rng, n)
        if rng.random() < 0.3:
            stacks[0] = 0
        if sum(stacks) == 0:
            stacks[1] = 5
        assert bubble_corrected_equity(stacks, PAYOUTS, 0.0) == pytest.approx(
            icm_equity(stacks, PAYOUTS))


def test_total_preserved():
    rng = np.random.default_rng(866)
    for _ in range(20):
        stacks = _random_stacks(rng, len(PAYOUTS) + 1)
        lam = float(rng.random())
        eq = bubble_corrected_equity(stacks, PAYOUTS, lam)
        assert sum(eq) == pytest.approx(sum(PAYOUTS))
        mean = np.mean(stacks)
        adjusted = [s + lam * mean for s in stacks]
        assert sum(eq) == pytest.approx(sum(icm_equity(adjusted, PAYOUTS)))


@pytest.mark.parametrize("stacks", [
    [100, 200, 300],             # in the money (m == K)
    [100, 200, 300, 400, 500],   # two places off the bubble (m == K+2)
    [100, 200, 0, 0, 0],         # deep in the money with busted players
])
def test_not_bubble_ignores_lambda(stacks):
    expected = icm_equity(stacks, PAYOUTS)
    for lam in (0.2, 0.5, 1.0):
        assert bubble_corrected_equity(stacks, PAYOUTS, lam) == pytest.approx(expected)


def test_busted_player_gets_zero_and_no_bonus():
    stacks = [0, 100, 200, 300, 400]   # 4 live = K+1: bubble
    eq = bubble_corrected_equity(stacks, PAYOUTS, 0.5)
    assert eq[0] == 0.0
    live_mean = np.mean([100, 200, 300, 400])
    adjusted = [0] + [s + 0.5 * live_mean for s in stacks[1:]]
    assert eq == pytest.approx(icm_equity(adjusted, PAYOUTS))


def test_bubble_lambda_raises_short_stack_equity():
    stacks = [100, 2000, 3000, 4000]
    base = icm_equity(stacks, PAYOUTS)
    for lam in (0.05, 0.2, 1.0):
        eq = bubble_corrected_equity(stacks, PAYOUTS, lam)
        assert eq[0] > base[0]


@pytest.mark.parametrize("lam", [-0.01, 1.01, math.nan, "x"])
def test_invalid_lambda_raises(lam):
    with pytest.raises(ValueError, match=r"lam must be"):
        bubble_corrected_equity([100, 200, 300, 400], PAYOUTS, lam)
