import math

import numpy as np
import pytest

from referee.stats import adjust_with_corrections
from stalker.toy import aivat as a


SEED = 1  # fixed seed: with c=z about 5% of seeds exceed 2*raw_se by chance


def _data(seed, noise, center=True):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, 4000)
    raw = 0.5 + z + rng.normal(0, 0.3, 4000)
    if noise is not None:
        c = rng.normal(0, noise, 4000)
    else:
        # center=False keeps the population-mean-0 term as drawn, so the sample mean is not forced to 0.
        c = z - z.mean() if center else z
    return raw, c


def test_mean_zero_correction_keeps_mean_within_two_se():
    raw, c = _data(SEED, None, center=False)
    r = adjust_with_corrections(raw, c)
    assert r.mean != r.raw_mean  # a nonzero shift, otherwise the check below is a constant
    assert abs(r.mean - r.raw_mean) <= 2 * r.raw_se
    assert r.n == 4000


def test_correlated_correction_lowers_variance_ratio():
    raw, c = _data(2, None)
    assert adjust_with_corrections(raw, c).var_ratio < 1


def test_unrelated_noise_correction_raises_variance_ratio():
    raw, c = _data(3, 1.0)
    assert adjust_with_corrections(raw, c).var_ratio > 1


@pytest.mark.parametrize("raw,c", [([1.0, 2.0], [0.0]), ([], []), ([1.0], [0.0]),
                                    ([1.0, float("nan")], [0.0, 0.0])])
def test_bad_input_raises_value_error(raw, c):
    with pytest.raises(ValueError):
        adjust_with_corrections(raw, c)


def test_matches_toy_aivat_simulation():
    raw, est = a.simulate(1500, np.random.default_rng(11), v=a.showdown_value(), known=frozenset({1, 2}))
    r = adjust_with_corrections(raw, raw - est)
    assert math.isclose(r.mean, est.mean(), rel_tol=1e-9)
    assert math.isclose(r.se, a.se(est), rel_tol=1e-9)


def test_constant_raw_ratio_is_defined():
    same = adjust_with_corrections([1.0] * 5, [0.0] * 5)
    assert same.var_ratio == 1.0
    assert adjust_with_corrections([1.0] * 5, [0.0, 1.0, 0.0, 1.0, 0.0]).var_ratio == math.inf
